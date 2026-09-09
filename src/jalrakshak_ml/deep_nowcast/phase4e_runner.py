"""GPU-capable, validation-only Phase 4E runner; importing never starts training."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch

from .losses import MultiScalePiecewiseLoss
from .splits import VALIDATION_EVENTS_AUTHORITATIVE, is_locked_test_event
from .tournament import evaluate_predictions


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_loader_allowed(loader, allowed: tuple[str, ...]) -> None:
    dataset = loader.dataset
    if getattr(dataset, "split", None) not in allowed:
        raise PermissionError(
            f"Runner permits only {allowed}, got {getattr(dataset, 'split', None)!r}"
        )
    for index in getattr(dataset, "indices", []):
        if is_locked_test_event(index.event_id):
            raise PermissionError("Locked-test sample entered Phase 4E runner")
    stats = getattr(dataset, "stats", None)
    if stats is not None and not getattr(stats, "is_final_phase4e_statistics", False):
        raise RuntimeError("Final train-only normalization artifact is required")


def event_block_bootstrap(
    event_metrics: dict[str, list[float]], *, seed: int = 26071, iterations: int = 2000
) -> dict[str, float]:
    """Bootstrap whole events/blocks; pixels are never treated as independent samples."""
    if len(event_metrics) < 2:
        raise ValueError("At least two events are required for an event bootstrap")
    values = [np.asarray(value, dtype=float) for value in event_metrics.values()]
    if any(not np.isfinite(value).all() for value in values):
        raise ValueError("Non-finite event metric")
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(iterations):
        sampled = rng.integers(0, len(values), len(values))
        estimates.append(float(np.mean(np.concatenate([values[i] for i in sampled]))))
    return {
        "estimate": float(np.mean(np.concatenate(values))),
        "ci_low": float(np.percentile(estimates, 2.5)),
        "ci_high": float(np.percentile(estimates, 97.5)),
        "unit": "event_or_event_block",
        "iterations": iterations,
    }


def compile_validation_comparison(
    model_event_data: dict[str, dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]],
    runtime_metadata: dict[str, dict[str, float | int]],
) -> dict[str, Any]:
    """Compile per-event/overall validation metrics and event-bootstrap intervals."""
    comparison = {}
    for model_name, events in model_event_data.items():
        if set(events) != set(VALIDATION_EVENTS_AUTHORITATIVE):
            raise ValueError(
                "Comparison requires exactly the three authoritative validation events"
            )
        if any(is_locked_test_event(event_id) for event_id in events):
            raise PermissionError("Locked test entered validation comparison")
        per_event, predictions, targets, masks = {}, [], [], []
        for event_id, (prediction, target, mask) in events.items():
            per_event[event_id] = evaluate_predictions(prediction, target, mask)
            predictions.append(prediction)
            targets.append(target)
            masks.append(mask)
        overall = evaluate_predictions(
            np.concatenate(predictions), np.concatenate(targets), np.concatenate(masks)
        )
        mae_blocks = {
            event_id: [metrics["overall"]["mae"]] for event_id, metrics in per_event.items()
        }
        rmse_blocks = {
            event_id: [metrics["overall"]["rmse"]] for event_id, metrics in per_event.items()
        }
        comparison[model_name] = {
            "overall": overall,
            "per_event": per_event,
            "confidence_intervals": {
                "mae": event_block_bootstrap(mae_blocks),
                "rmse": event_block_bootstrap(rmse_blocks),
            },
            "latency_and_size": runtime_metadata[model_name],
        }
    return {
        "split": "validation",
        "events": list(VALIDATION_EVENTS_AUTHORITATIVE),
        "models": comparison,
        "bootstrap_unit": "event",
        "pixel_independence_assumed": False,
        "locked_test_accessed": False,
    }


@dataclass
class RunnerConfig:
    checkpoint_root: Path
    epochs: int = 40
    batch_size: int = 4
    patience: int = 6
    learning_rate: float = 1e-3
    use_amp: bool = True


class ValidationOnlyRunner:
    """Train on train, select/evaluate on validation, and never construct test data."""

    def __init__(
        self, config: RunnerConfig, *, git_sha: str, config_hash: str, normalization_hash: str
    ):
        self.config = config
        self.git_sha = git_sha
        self.config_hash = config_hash
        self.normalization_hash = normalization_hash

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
        if seed not in (26071, 26072, 26073):
            raise ValueError("Unapproved Phase 4E seed")
        torch.manual_seed(seed)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model_factory().to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.config.learning_rate)
        criterion = MultiScalePiecewiseLoss()
        scaler = torch.amp.GradScaler("cuda", enabled=self.config.use_amp and device.type == "cuda")
        directory = self.config.checkpoint_root / architecture / f"seed_{seed}"
        directory.mkdir(parents=True, exist_ok=True)
        latest, best = directory / "latest.pt", directory / "best.pt"
        start_epoch, best_mae, stale = 1, float("inf"), 0
        if latest.exists():
            state = torch.load(latest, map_location=device, weights_only=False)
            model.load_state_dict(state["model"])
            optimizer.load_state_dict(state["optimizer"])
            scaler.load_state_dict(state["scaler"])
            start_epoch, best_mae, stale = state["epoch"] + 1, state["best_mae"], state["stale"]
        started, history = time.perf_counter(), []
        for epoch in range(start_epoch, self.config.epochs + 1):
            model.train()
            losses = []
            for batch in train_loader:
                try:
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast(
                        device_type=device.type,
                        enabled=self.config.use_amp and device.type == "cuda",
                    ):
                        prediction = model(
                            obs_history=batch["obs_history"].to(device),
                            nwp_future=batch["nwp_future"].to(device),
                            static_features=batch["static_features"].to(device),
                            persistence_baseline=batch["persistence_baseline"].to(device),
                            missing_channel_mask=batch["missing_channel_mask"].to(device),
                        )
                        loss = criterion(
                            prediction,
                            batch["target_physical"].to(device),
                            batch["target_mask"].to(device),
                        )
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                    losses.append(float(loss.detach().cpu()))
                except torch.cuda.OutOfMemoryError as error:
                    optimizer.zero_grad(set_to_none=True)
                    torch.cuda.empty_cache()
                    size = batch["obs_history"].shape[0]
                    fallback = max(1, size // 2)
                    if fallback == size:
                        raise RuntimeError("CUDA OOM at batch size 1") from error
                    parts = (size + fallback - 1) // fallback
                    for start in range(0, size, fallback):
                        slc = slice(start, min(size, start + fallback))
                        with torch.autocast(
                            device_type=device.type,
                            enabled=self.config.use_amp and device.type == "cuda",
                        ):
                            prediction = model(
                                obs_history=batch["obs_history"][slc].to(device),
                                nwp_future=batch["nwp_future"][slc].to(device),
                                static_features=batch["static_features"][slc].to(device),
                                persistence_baseline=batch["persistence_baseline"][slc].to(device),
                                missing_channel_mask=batch["missing_channel_mask"][slc].to(device),
                            )
                            loss = (
                                criterion(
                                    prediction,
                                    batch["target_physical"][slc].to(device),
                                    batch["target_mask"][slc].to(device),
                                )
                                / parts
                            )
                        scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                    losses.append(float(loss.detach().cpu()) * parts)
            metrics = self.evaluate(model, validation_loader, device)
            mae = metrics["overall"]["mae"]
            improved = mae < best_mae
            best_mae, stale = (mae, 0) if improved else (best_mae, stale + 1)
            checkpoint = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "epoch": epoch,
                "best_mae": best_mae,
                "stale": stale,
                "seed": seed,
                "architecture": architecture,
                "git_sha": self.git_sha,
                "config_hash": self.config_hash,
                "normalization_hash": self.normalization_hash,
            }
            part = latest.with_suffix(".pt.part")
            torch.save(checkpoint, part)
            part.replace(latest)
            if improved:
                best_part = best.with_suffix(".pt.part")
                torch.save(checkpoint, best_part)
                best_part.replace(best)
            history.append(
                {"epoch": epoch, "train_loss": float(np.mean(losses)), "validation": metrics}
            )
            if stale >= self.config.patience:
                break
        return {
            "architecture": architecture,
            "seed": seed,
            "device": str(device),
            "parameter_count": sum(p.numel() for p in model.parameters()),
            "runtime_seconds": time.perf_counter() - started,
            "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated()
            if device.type == "cuda"
            else 0,
            "best_checkpoint": str(best),
            "best_checkpoint_sha256": _hash(best),
            "history": history,
            "locked_test_accessed": False,
        }

    @staticmethod
    def evaluate(model, loader, device) -> dict[str, Any]:
        _assert_loader_allowed(loader, ("validation",))
        model.eval()
        predictions, targets, masks = [], [], []
        with torch.no_grad():
            for batch in loader:
                prediction = model(
                    obs_history=batch["obs_history"].to(device),
                    nwp_future=batch["nwp_future"].to(device),
                    static_features=batch["static_features"].to(device),
                    persistence_baseline=batch["persistence_baseline"].to(device),
                    missing_channel_mask=batch["missing_channel_mask"].to(device),
                )
                predictions.append(prediction.cpu().numpy())
                targets.append(batch["target_physical"].numpy())
                masks.append(batch["target_mask"].numpy())
        return evaluate_predictions(
            np.concatenate(predictions), np.concatenate(targets), np.concatenate(masks)
        )
