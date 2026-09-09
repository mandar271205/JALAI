"""Reproducible GPU-capable, validation-only Phase 4E training stack."""

from __future__ import annotations

import hashlib
import os
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from .final_contracts import NWP_CHANNEL_ORDER, SEEDS
from .losses import MultiScalePiecewiseLoss
from .phase4e_runner import compile_validation_comparison, event_block_bootstrap
from .splits import is_locked_test_event


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_everything(seed: int, *, deterministic: bool = True) -> dict[str, Any]:
    if seed not in SEEDS:
        raise ValueError("Unapproved Phase 4E seed")
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = deterministic
    torch.backends.cudnn.benchmark = not deterministic
    torch.use_deterministic_algorithms(deterministic, warn_only=True)
    return {
        "python_seed": seed,
        "numpy_seed": seed,
        "torch_cpu_seed": seed,
        "torch_cuda_seed": seed,
        "deterministic_algorithms": deterministic,
        "cudnn_benchmark": not deterministic,
    }


def seed_worker(worker_id: int) -> None:
    del worker_id
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def make_dataloader(dataset, *, batch_size: int, seed: int, shuffle: bool) -> DataLoader:
    generator = torch.Generator().manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
        worker_init_fn=seed_worker,
        num_workers=0,
    )


def _assert_loader_allowed(loader, allowed: tuple[str, ...]) -> None:
    dataset = loader.dataset
    split = getattr(dataset, "split", None)
    if split not in allowed:
        raise PermissionError(f"Runner permits only {allowed}, got {split!r}")
    if any(is_locked_test_event(index.event_id) for index in getattr(dataset, "indices", [])):
        raise PermissionError("Locked-test sample entered Phase 4E runner")
    if tuple(getattr(dataset, "nwp_channel_order", ())) != NWP_CHANNEL_ORDER:
        raise ValueError("Runner dataset does not declare the exact final NWP channel order")
    stats = getattr(dataset, "stats", None)
    if stats is None or getattr(stats, "artifact", {}).get("status") != "PASS":
        raise RuntimeError("Final train-only normalization artifact is required")


@dataclass(frozen=True)
class RunnerConfig:
    checkpoint_root: Path
    epochs: int = 40
    batch_size: int = 4
    patience: int = 6
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    gradient_clip_norm: float = 1.0
    scheduler_patience: int = 2
    scheduler_factor: float = 0.5
    use_amp: bool = True
    deterministic: bool = True


class FinalValidationRunner:
    """Train on train and early-stop on validation; there is deliberately no test method."""

    def __init__(
        self,
        config: RunnerConfig,
        *,
        git_sha: str,
        config_hash: str,
        normalization_hash: str,
        replay_manifest_hash: str,
    ) -> None:
        self.config = config
        self.git_sha = git_sha
        self.config_hash = config_hash
        self.normalization_hash = normalization_hash
        self.replay_manifest_hash = replay_manifest_hash

    @staticmethod
    def _call(model, batch, device):
        return model(
            obs_history=batch["obs_history"].to(device),
            nwp_future=batch["nwp_future"].to(device),
            static_features=batch["static_features"].to(device),
            persistence_baseline=batch["persistence_baseline"].to(device),
            missing_obs_mask=batch["missing_obs_mask"].to(device),
            missing_nwp_mask=batch["missing_nwp_mask"].to(device),
            missing_static_mask=batch["missing_static_mask"].to(device),
        )

    def _compatibility(self, architecture: str, seed: int, model) -> dict[str, Any]:
        return {
            "architecture": architecture,
            "model_version": model.model_version,
            "model_config": model.config_dict(),
            "seed": seed,
            "config_hash": self.config_hash,
            "normalization_hash": self.normalization_hash,
            "replay_manifest_hash": self.replay_manifest_hash,
            "git_commit": self.git_sha,
        }

    @staticmethod
    def validate_resume_checkpoint(
        state: dict[str, Any], expected_compatibility: dict[str, Any]
    ) -> None:
        required = {
            "model",
            "optimizer",
            "scheduler",
            "scaler",
            "epoch",
            "best_mae",
            "best_epoch",
            "stale",
            "rng_state",
            "compatibility",
        }
        missing = required - set(state)
        if missing:
            raise ValueError(f"Resume checkpoint is incomplete: {sorted(missing)}")
        if state["compatibility"] != expected_compatibility:
            raise ValueError("Resume checkpoint is incompatible with this run")

    @staticmethod
    def atomic_checkpoint(payload: dict[str, Any], destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        torch.save(payload, part)
        part.replace(destination)

    def train(
        self,
        model_factory: Callable[[], torch.nn.Module],
        train_loader,
        validation_loader,
        *,
        architecture: str,
        seed: int,
    ) -> dict[str, Any]:
        _assert_loader_allowed(train_loader, ("train",))
        _assert_loader_allowed(validation_loader, ("validation",))
        reproducibility = seed_everything(seed, deterministic=self.config.deterministic)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats()
        model = model_factory().to(device)
        compatibility = self._compatibility(architecture, seed, model)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            patience=self.config.scheduler_patience,
            factor=self.config.scheduler_factor,
        )
        criterion = MultiScalePiecewiseLoss()
        amp_enabled = self.config.use_amp and device.type == "cuda"
        scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
        directory = self.config.checkpoint_root / architecture / f"seed_{seed}"
        latest, best = directory / "latest.pt", directory / "best.pt"
        start_epoch, best_mae, best_epoch, stale = 1, float("inf"), 0, 0
        resume_used = False
        if latest.exists():
            state = torch.load(latest, map_location=device, weights_only=False)
            self.validate_resume_checkpoint(state, compatibility)
            model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            scheduler.load_state_dict(state["scheduler"])
            scaler.load_state_dict(state["scaler"])
            start_epoch = int(state["epoch"]) + 1
            best_mae, best_epoch, stale = state["best_mae"], state["best_epoch"], state["stale"]
            random.setstate(state["rng_state"]["python"])
            np.random.set_state(state["rng_state"]["numpy"])
            torch.set_rng_state(state["rng_state"]["torch_cpu"])
            if device.type == "cuda" and state["rng_state"].get("torch_cuda"):
                torch.cuda.set_rng_state_all(state["rng_state"]["torch_cuda"])
            resume_used = True

        started, history, oom_fallbacks = time.perf_counter(), [], []
        stop_reason, final_epoch = "max_epochs", start_epoch - 1
        for epoch in range(start_epoch, self.config.epochs + 1):
            final_epoch = epoch
            model.train()
            losses = []
            for batch_index, batch in enumerate(train_loader):
                try:
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast(device_type=device.type, enabled=amp_enabled):
                        prediction = self._call(model, batch, device)
                        loss = criterion(
                            prediction,
                            batch["target_physical"].to(device),
                            batch["target_mask"].to(device),
                        )
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), self.config.gradient_clip_norm
                    )
                    scaler.step(optimizer)
                    scaler.update()
                    losses.append(float(loss.detach().cpu()))
                except torch.cuda.OutOfMemoryError as error:
                    optimizer.zero_grad(set_to_none=True)
                    torch.cuda.empty_cache()
                    batch_size = int(batch["obs_history"].shape[0])
                    microbatch = max(1, batch_size // 2)
                    if microbatch == batch_size:
                        raise RuntimeError("CUDA OOM at batch size 1") from error
                    chunks = (batch_size + microbatch - 1) // microbatch
                    oom_fallbacks.append(
                        {"epoch": epoch, "batch": batch_index, "from": batch_size, "to": microbatch}
                    )
                    for start in range(0, batch_size, microbatch):
                        sliced = {
                            key: value[start : start + microbatch]
                            if isinstance(value, torch.Tensor)
                            else value
                            for key, value in batch.items()
                        }
                        with torch.autocast(device_type=device.type, enabled=amp_enabled):
                            loss = (
                                criterion(
                                    self._call(model, sliced, device),
                                    sliced["target_physical"].to(device),
                                    sliced["target_mask"].to(device),
                                )
                                / chunks
                            )
                        scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), self.config.gradient_clip_norm
                    )
                    scaler.step(optimizer)
                    scaler.update()
                    losses.append(float(loss.detach().cpu()) * chunks)

            validation = self.evaluate(model, validation_loader, device)
            mae = float(validation["overall"]["mae"])
            scheduler.step(mae)
            improved = mae < best_mae
            if improved:
                best_mae, best_epoch, stale = mae, epoch, 0
            else:
                stale += 1
            checkpoint = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict(),
                "epoch": epoch,
                "best_mae": best_mae,
                "best_epoch": best_epoch,
                "stale": stale,
                "compatibility": compatibility,
                "runner_config": asdict(self.config),
                "validation_score": mae,
                "rng_state": {
                    "python": random.getstate(),
                    "numpy": np.random.get_state(),
                    "torch_cpu": torch.get_rng_state(),
                    "torch_cuda": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
                },
            }
            self.atomic_checkpoint(checkpoint, latest)
            if improved:
                self.atomic_checkpoint(checkpoint, best)
            history.append(
                {"epoch": epoch, "train_loss": float(np.mean(losses)), "validation": validation}
            )
            if stale >= self.config.patience:
                stop_reason = "validation_early_stopping"
                break

        if not best.is_file():
            raise RuntimeError("Training produced no best validation checkpoint")
        device_metadata = {
            "device": str(device),
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": torch.cuda.get_device_name(device)
            if device.type == "cuda"
            else None,
            "torch_version": torch.__version__,
            "amp_enabled": amp_enabled,
        }
        return {
            "architecture": architecture,
            "seed": seed,
            "reproducibility": reproducibility,
            "device_metadata": device_metadata,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "runtime_seconds": time.perf_counter() - started,
            "peak_gpu_memory_bytes": (
                torch.cuda.max_memory_allocated() if device.type == "cuda" else 0
            ),
            "train_sample_count": len(train_loader.dataset),
            "validation_sample_count": len(validation_loader.dataset),
            "epochs_completed": max(0, final_epoch - start_epoch + 1),
            "best_epoch": best_epoch,
            "final_epoch": final_epoch,
            "stop_reason": stop_reason,
            "monitored_metric": "validation.overall.mae",
            "resume_used": resume_used,
            "oom_microbatch_fallbacks": oom_fallbacks,
            "latest_checkpoint": str(latest),
            "latest_checkpoint_sha256": _hash(latest),
            "best_checkpoint": str(best),
            "best_checkpoint_sha256": _hash(best),
            "history": history,
            "locked_test_accessed": False,
        }

    @classmethod
    def evaluate(cls, model, loader, device) -> dict[str, Any]:
        from .tournament import evaluate_predictions

        _assert_loader_allowed(loader, ("validation",))
        model.eval()
        predictions, targets, masks = [], [], []
        with torch.no_grad():
            for batch in loader:
                predictions.append(cls._call(model, batch, device).cpu().numpy())
                targets.append(batch["target_physical"].numpy())
                masks.append(batch["target_mask"].numpy())
        return evaluate_predictions(
            np.concatenate(predictions), np.concatenate(targets), np.concatenate(masks)
        )


__all__ = [
    "FinalValidationRunner",
    "RunnerConfig",
    "compile_validation_comparison",
    "event_block_bootstrap",
    "make_dataloader",
    "seed_everything",
]
