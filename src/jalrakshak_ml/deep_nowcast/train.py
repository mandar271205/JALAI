"""Reproducible ConvLSTM training, validation, checkpointing, and resume."""
from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn.utils import clip_grad_norm_
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, build_datasets_from_config
from jalrakshak_ml.deep_nowcast.losses import WeightedRainfallLoss
from jalrakshak_ml.utils.hashing import sha256_file


@dataclass(slots=True)
class TrainingOutcome:
    best_checkpoint: Path
    latest_checkpoint: Path
    history_json: Path
    history_csv: Path
    metadata_json: Path
    best_validation_loss: float
    epochs_completed: int
    checkpoint_hash: str
    device: str


def set_reproducible_seed(seed: int, deterministic: bool = True) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.use_deterministic_algorithms(True, warn_only=True)
        if torch.backends.cudnn.is_available():
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True


def resolve_device(requested: str = "auto") -> torch.device:
    requested = requested.lower()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return torch.device(requested)


def _run_epoch(
    model: ConvLSTMNowcaster,
    loader: DataLoader,
    criterion: WeightedRainfallLoss,
    device: torch.device,
    *,
    optimizer: torch.optim.Optimizer | None = None,
    gradient_clip_norm: float | None = None,
) -> float:
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_samples = 0
    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for batch in loader:
            inputs = batch["inputs"].to(device=device, dtype=torch.float32)
            target = batch["target"].to(device=device, dtype=torch.float32)
            target_mask = batch["target_mask"].to(device=device, dtype=torch.bool)
            if training:
                optimizer.zero_grad(set_to_none=True)
            prediction = model(inputs)
            loss = criterion(prediction, target, target_mask)
            if training:
                loss.backward()
                if gradient_clip_norm is not None:
                    clip_grad_norm_(model.parameters(), gradient_clip_norm)
                optimizer.step()
            batch_size = inputs.shape[0]
            total_loss += float(loss.detach().cpu()) * batch_size
            total_samples += batch_size
    if total_samples == 0:
        raise ValueError("DataLoader produced no samples placable into an epoch")
    return total_loss / total_samples


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    torch.save(payload, temp)
    os.replace(temp, path)


def _write_history(history: list[dict[str, Any]], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(history, indent=2, allow_nan=False), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)


def train_model(
    model: ConvLSTMNowcaster,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    *,
    normalizer: LogRainNormalizer,
    output_dir: str | Path,
    data_version: str,
    model_version: str,
    epochs: int = 20,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    event_threshold_mm_h: float = 5.0,
    event_weight: float = 4.0,
    mse_weight: float = 0.25,
    gradient_clip_norm: float = 1.0,
    early_stopping_patience: int = 5,
    scheduler_patience: int = 2,
    scheduler_factor: float = 0.5,
    device: str | torch.device = "auto",
    seed: int = 26071,
    resume_from: str | Path | None = None,
) -> TrainingOutcome:
    """Train and checkpoint a model; suitable for both Colab and CPU smoke tests."""
    if epochs < 1:
        raise ValueError("epochs must be >= 1")
    set_reproducible_seed(seed)
    device_obj = resolve_device(device) if isinstance(device, str) else device
    model = model.to(device_obj)
    criterion = WeightedRainfallLoss(
        heavy_threshold=normalizer.transform_scalar(event_threshold_mm_h),
        heavy_weight=event_weight,
        mse_weight=mse_weight,
    )
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=scheduler_factor,
        patience=scheduler_patience,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    best_path = output_dir / "best.pt"
    latest_path = output_dir / "latest.pt"
    history_json = output_dir / "training_history.json"
    history_csv = output_dir / "training_history.csv"
    metadata_json = output_dir / "training_metadata.json"
    start_epoch = 0
    best_loss = float("inf")
    epochs_without_improvement = 0
    history: list[dict[str, Any]] = []

    if resume_from is not None:
        checkpoint = torch.load(Path(resume_from), map_location=device_obj, weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if checkpoint.get("scheduler_state_dict"):
            scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        if checkpoint.get("data_version") != data_version:
            raise ValueError("Resume checkpoint data_version does not match the active dataset")
        start_epoch = int(checkpoint["epoch"]) + 1
        best_loss = float(checkpoint["best_validation_loss"])
        epochs_without_improvement = int(checkpoint.get("epochs_without_improvement", 0))
        history = list(checkpoint.get("history", []))

    for epoch in range(start_epoch, epochs):
        train_loss = _run_epoch(
            model,
            train_loader,
            criterion,
            device_obj,
            optimizer=optimizer,
            gradient_clip_norm=gradient_clip_norm,
        )
        validation_loss = _run_epoch(model, validation_loader, criterion, device_obj)
        scheduler.step(validation_loss)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
        }
        history.append(row)
        improved = validation_loss < best_loss
        if improved:
            best_loss = validation_loss
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        payload = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "best_validation_loss": best_loss,
            "epochs_without_improvement": epochs_without_improvement,
            "history": history,
            "model_config": model.config_dict(),
            "normalizer": normalizer.to_dict(),
            "model_version": model_version,
            "data_version": data_version,
            "seed": seed,
            "created_at": datetime.now(UTC).isoformat(),
            "forecast_type": "deterministic",
            "loss": {
                "name": "weighted_mae_plus_mse",
                "event_threshold_mm_h": event_threshold_mm_h,
                "event_weight": event_weight,
                "mse_weight": mse_weight,
            },
        }
        _save_checkpoint(latest_path, payload)
        if improved:
            _save_checkpoint(best_path, payload)
        _write_history(history, history_json, history_csv)
        if epochs_without_improvement >= early_stopping_patience:
            break

    if not best_path.exists():
        raise RuntimeError("Training completed without a best checkpoint")
    metadata = {
        "model_version": model_version,
        "data_version": data_version,
        "device": str(device_obj),
        "cuda_available": torch.cuda.is_available(),
        "best_checkpoint": str(best_path.resolve()),
        "best_checkpoint_sha256": sha256_file(best_path),
        "best_validation_loss": best_loss,
        "epochs_completed": len(history),
        "normalizer": normalizer.to_dict(),
        "model_config": model.config_dict(),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    metadata_json.write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    return TrainingOutcome(
        best_checkpoint=best_path,
        latest_checkpoint=latest_path,
        history_json=history_json,
        history_csv=history_csv,
        metadata_json=metadata_json,
        best_validation_loss=best_loss,
        epochs_completed=len(history),
        checkpoint_hash=metadata["best_checkpoint_sha256"],
        device=str(device_obj),
    )


def train_from_config(
    config_path: str | Path,
    *,
    device_override: str | None = None,
    resume_from: str | Path | None = None,
) -> TrainingOutcome:
    config_path = Path(config_path).resolve()
    config = load_yaml(config_path)
    repo_root = config_path.parents[2]
    datasets, normalizer = build_datasets_from_config(config_path)
    if any(len(dataset) == 0 for dataset in datasets.values()):
        sizes = {name: len(dataset) for name, dataset in datasets.items()}
        raise RuntimeError(f"Every event-isolated split needs at least one sequence; got {sizes}")
    training = config["training"]
    seed = int(training["seed"])
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(
        datasets["train"],
        batch_size=int(training["batch_size"]),
        shuffle=True,
        num_workers=int(training.get("num_workers", 0)),
        generator=generator,
    )
    validation_loader = DataLoader(
        datasets["validation"],
        batch_size=int(training["batch_size"]),
        shuffle=False,
        num_workers=int(training.get("num_workers", 0)),
    )
    model_cfg = config["model"]
    model = ConvLSTMNowcaster(
        input_channels=len(config["dataset"]["input_channels"]),
        hidden_channels=model_cfg["hidden_channels"],
        num_layers=int(model_cfg["num_layers"]),
        output_horizons=int(config["dataset"]["prediction_horizon"]),
        output_channels=1,
        kernel_size=int(model_cfg.get("kernel_size", 3)),
        head_channels=int(model_cfg.get("head_channels", 16)),
    )
    output_dir = repo_root / config["artifacts"]["model_dir"] / config["model"]["version"]
    return train_model(
        model,
        train_loader,
        validation_loader,
        normalizer=normalizer,
        output_dir=output_dir,
        data_version=config["data"]["version"],
        model_version=config["model"]["version"],
        epochs=int(training["epochs"]),
        learning_rate=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        event_threshold_mm_h=float(training["loss"]["event_threshold_mm_h"]),
        event_weight=float(training["loss"]["event_weight"]),
        mse_weight=float(training["loss"]["mse_weight"]),
        gradient_clip_norm=float(training["gradient_clip_norm"]),
        early_stopping_patience=int(training["early_stopping_patience"]),
        scheduler_patience=int(training["scheduler"]["patience"]),
        scheduler_factor=float(training["scheduler"]["factor"]),
        device=device_override or str(training.get("device", "auto")),
        seed=seed,
        resume_from=resume_from,
    )
