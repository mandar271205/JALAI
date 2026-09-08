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
from torch import nn
from torch.nn.utils import clip_grad_norm_
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.dataset import (
    LogRainNormalizer,
    build_dataloaders,
    build_datasets_from_config,
)
from jalrakshak_ml.deep_nowcast.losses import HeavyRainAwareLoss, WeightedRainfallLoss
from jalrakshak_ml.deep_nowcast.residual_convlstm import (
    PersistenceResidualConvLSTMNowcaster,
)
from jalrakshak_ml.deep_nowcast.verification import pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.utils.hashing import sha256_file


@dataclass(slots=True)
class TrainingOutcome:
    best_checkpoint: Path
    latest_checkpoint: Path
    history_json: Path
    history_csv: Path
    metadata_json: Path
    best_validation_loss: float
    best_validation_score: float
    best_validation_metrics: dict[str, Any]
    best_epoch: int
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


def compute_validation_score(metrics: dict[str, Any], config: dict[str, Any]) -> float:
    """Score pooled validation skill, safely treating absent heavy rain as no skill."""
    overall = metrics.get("overall", {})
    mae = overall.get("mae")
    if mae is None or not np.isfinite(float(mae)):
        return float("-inf")
    suffix = str(float(config.get("heavy_threshold_mm_h", 5.0)))
    coefficients = config.get("weights", {})
    csi = overall.get(f"csi_{suffix}")
    pod = overall.get(f"pod_{suffix}")
    far = overall.get(f"far_{suffix}")
    score = -float(coefficients.get("mae", 1.0)) * float(mae)
    score += float(coefficients.get("csi", 1.0)) * (0.0 if csi is None else float(csi))
    score += float(coefficients.get("pod", 1.0)) * (0.0 if pod is None else float(pod))
    score -= float(coefficients.get("far", 1.0)) * (0.0 if far is None else float(far))
    return score


def _model_predictions(
    model: nn.Module,
    batch: dict[str, Any],
    inputs: torch.Tensor,
    normalizer: LogRainNormalizer,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    if isinstance(model, PersistenceResidualConvLSTMNowcaster):
        baseline = batch["persistence_baseline"].to(device=device, dtype=torch.float32)
        target_physical = batch["target_physical"].to(device=device, dtype=torch.float32)
        prediction_physical = model(inputs, baseline)
        return prediction_physical, target_physical, prediction_physical
    target_normalized = batch["target"].to(device=device, dtype=torch.float32)
    prediction_normalized = model(inputs)
    prediction_physical = normalizer.inverse(prediction_normalized)
    return prediction_normalized, target_normalized, prediction_physical


def _run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    normalizer: LogRainNormalizer,
    device: torch.device,
    *,
    thresholds: list[float],
    optimizer: torch.optim.Optimizer | None = None,
    gradient_clip_norm: float | None = None,
) -> tuple[float, list[list[dict[str, Any]]]]:
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_samples = 0
    metric_rows: list[list[dict[str, Any]]] = []
    evaluator = NowcastEvaluator(thresholds=thresholds)
    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for batch in loader:
            inputs = batch["inputs"].to(device=device, dtype=torch.float32)
            target_mask = batch["target_mask"].to(device=device, dtype=torch.bool)
            if training:
                optimizer.zero_grad(set_to_none=True)
            prediction_loss, target_loss, prediction_physical = _model_predictions(
                model, batch, inputs, normalizer, device
            )
            loss = criterion(prediction_loss, target_loss, target_mask)
            if training:
                loss.backward()
                if gradient_clip_norm is not None:
                    clip_grad_norm_(model.parameters(), gradient_clip_norm)
                optimizer.step()
            batch_size = inputs.shape[0]
            total_loss += float(loss.detach().cpu()) * batch_size
            total_samples += batch_size
            if not training:
                observation = batch["target_physical"].numpy()[:, :, 0]
                predicted = prediction_physical.detach().cpu().numpy()[:, :, 0]
                masks = batch["target_mask"].numpy()[:, :, 0].astype(bool)
                for sample in range(batch_size):
                    frame = evaluator.evaluate_sequence(
                        observation[sample], predicted[sample], valid_mask=masks[sample]
                    )
                    metric_rows.append(frame.to_dict(orient="records"))
    if total_samples == 0:
        raise ValueError("DataLoader produced no samples placable into an epoch")
    return total_loss / total_samples, metric_rows


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    torch.save(payload, temporary)
    os.replace(temporary, path)


def _write_history(history: list[dict[str, Any]], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(history, indent=2, allow_nan=False), encoding="utf-8")
    fields = list(dict.fromkeys(key for row in history for key in row))
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(history)


def train_model(
    model: nn.Module,
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
    intensity_thresholds_mm_h: list[float] | None = None,
    intensity_weights: list[float] | None = None,
    validation_thresholds_mm_h: list[float] | None = None,
    validation_score_config: dict[str, Any] | None = None,
    sampling_metadata: dict[str, Any] | None = None,
    gradient_clip_norm: float = 1.0,
    early_stopping_patience: int = 5,
    scheduler_patience: int = 2,
    scheduler_factor: float = 0.5,
    device: str | torch.device = "auto",
    seed: int = 26071,
    resume_from: str | Path | None = None,
) -> TrainingOutcome:
    """Train V1 or V2 while selecting V2 checkpoints by validation skill."""
    if epochs < 1:
        raise ValueError("epochs must be >= 1")
    set_reproducible_seed(seed)
    device_obj = resolve_device(device) if isinstance(device, str) else device
    model = model.to(device_obj)
    residual_mode = isinstance(model, PersistenceResidualConvLSTMNowcaster)
    thresholds = validation_thresholds_mm_h or [0.1, 1.0, 5.0]
    if residual_mode:
        criterion: nn.Module = HeavyRainAwareLoss(
            thresholds_mm_h=intensity_thresholds_mm_h or [1.0, 5.0, 10.0],
            weights=intensity_weights or [1.0, 2.0, 6.0, 10.0],
            mse_weight=mse_weight,
        )
        loss_metadata = {
            "name": "physical_piecewise_weighted_mae_plus_mse",
            "thresholds_mm_h": intensity_thresholds_mm_h or [1.0, 5.0, 10.0],
            "weights": intensity_weights or [1.0, 2.0, 6.0, 10.0],
            "mse_weight": mse_weight,
        }
    else:
        criterion = WeightedRainfallLoss(
            heavy_threshold=normalizer.transform_scalar(event_threshold_mm_h),
            heavy_weight=event_weight,
            mse_weight=mse_weight,
        )
        loss_metadata = {
            "name": "weighted_mae_plus_mse",
            "event_threshold_mm_h": event_threshold_mm_h,
            "event_weight": event_weight,
            "mse_weight": mse_weight,
        }

    score_selection = residual_mode and validation_score_config is not None
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = ReduceLROnPlateau(
        optimizer,
        mode="max" if score_selection else "min",
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
    best_score = float("-inf")
    best_metrics: dict[str, Any] = {}
    best_epoch = -1
    epochs_without_improvement = 0
    history: list[dict[str, Any]] = []

    if resume_from is not None:
        checkpoint = torch.load(Path(resume_from), map_location=device_obj, weights_only=False)
        if checkpoint.get("data_version") != data_version:
            raise ValueError("Resume checkpoint data_version does not match the active dataset")
        if checkpoint.get("model_version") != model_version:
            raise ValueError("Resume checkpoint model_version does not match the active model")
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if checkpoint.get("scheduler_state_dict"):
            scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_loss = float(checkpoint["best_validation_loss"])
        best_score = float(checkpoint.get("best_validation_score", -best_loss))
        best_metrics = dict(checkpoint.get("best_validation_metrics", {}))
        best_epoch = int(checkpoint.get("best_epoch", checkpoint["epoch"]))
        epochs_without_improvement = int(checkpoint.get("epochs_without_improvement", 0))
        history = list(checkpoint.get("history", []))

    for epoch in range(start_epoch, epochs):
        train_loss, _ = _run_epoch(
            model,
            train_loader,
            criterion,
            normalizer,
            device_obj,
            thresholds=thresholds,
            optimizer=optimizer,
            gradient_clip_norm=gradient_clip_norm,
        )
        validation_loss, validation_rows = _run_epoch(
            model,
            validation_loader,
            criterion,
            normalizer,
            device_obj,
            thresholds=thresholds,
        )
        validation_metrics = pool_metric_rows(validation_rows, thresholds)
        validation_score = (
            compute_validation_score(validation_metrics, validation_score_config or {})
            if score_selection
            else -validation_loss
        )
        scheduler.step(validation_score if score_selection else validation_loss)
        suffix = str(float((validation_score_config or {}).get("heavy_threshold_mm_h", 5.0)))
        overall = validation_metrics["overall"]
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_score": validation_score,
            "validation_mae": overall.get("mae"),
            "validation_rmse": overall.get("rmse"),
            "validation_pod_heavy": overall.get(f"pod_{suffix}"),
            "validation_far_heavy": overall.get(f"far_{suffix}"),
            "validation_csi_heavy": overall.get(f"csi_{suffix}"),
            "validation_f1_heavy": overall.get(f"f1_{suffix}"),
            "validation_bias_heavy": overall.get(f"bias_{suffix}"),
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
        }
        history.append(row)
        improved = validation_score > best_score if score_selection else validation_loss < best_loss
        if improved:
            best_loss = validation_loss
            best_score = validation_score
            best_metrics = validation_metrics
            best_epoch = epoch
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1

        payload = {
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "best_validation_loss": best_loss,
            "best_validation_score": best_score,
            "best_validation_metrics": best_metrics,
            "best_epoch": best_epoch,
            "epochs_without_improvement": epochs_without_improvement,
            "history": history,
            "model_config": model.config_dict(),
            "normalizer": normalizer.to_dict(),
            "model_version": model_version,
            "data_version": data_version,
            "seed": seed,
            "created_at": datetime.now(UTC).isoformat(),
            "forecast_type": (
                "deterministic_persistence_residual" if residual_mode else "deterministic"
            ),
            "loss": loss_metadata,
            "validation_score_config": validation_score_config,
            "sampling": sampling_metadata,
        }
        _save_checkpoint(latest_path, payload)
        if improved:
            _save_checkpoint(best_path, payload)
        _write_history(history, history_json, history_csv)
        if epochs_without_improvement >= early_stopping_patience:
            break

    if not best_path.exists() or best_epoch < 0:
        raise RuntimeError("Training completed without a best checkpoint")
    metadata = {
        "model_version": model_version,
        "data_version": data_version,
        "device": str(device_obj),
        "cuda_available": torch.cuda.is_available(),
        "best_checkpoint": str(best_path.resolve()),
        "best_checkpoint_sha256": sha256_file(best_path),
        "best_validation_loss": best_loss,
        "best_validation_score": best_score,
        "best_validation_metrics": best_metrics,
        "best_epoch": best_epoch,
        "epochs_completed": len(history),
        "normalizer": normalizer.to_dict(),
        "model_config": model.config_dict(),
        "loss": loss_metadata,
        "validation_score_config": validation_score_config,
        "sampling": sampling_metadata,
        "generated_at": datetime.now(UTC).isoformat(),
        "PHASE_3_MODEL_VALIDATED": False,
    }
    metadata_json.write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    return TrainingOutcome(
        best_checkpoint=best_path,
        latest_checkpoint=latest_path,
        history_json=history_json,
        history_csv=history_csv,
        metadata_json=metadata_json,
        best_validation_loss=best_loss,
        best_validation_score=best_score,
        best_validation_metrics=best_metrics,
        best_epoch=best_epoch,
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
    loaders, sampling_metadata = build_dataloaders(datasets, training)
    model_cfg = config["model"]
    model_arguments = {
        "input_channels": len(config["dataset"]["input_channels"]),
        "hidden_channels": model_cfg["hidden_channels"],
        "num_layers": int(model_cfg["num_layers"]),
        "output_horizons": int(config["dataset"]["prediction_horizon"]),
        "output_channels": 1,
        "kernel_size": int(model_cfg.get("kernel_size", 3)),
        "head_channels": int(model_cfg.get("head_channels", 16)),
    }
    if model_cfg.get("forecast_mode") == PersistenceResidualConvLSTMNowcaster.forecast_mode:
        model: nn.Module = PersistenceResidualConvLSTMNowcaster(**model_arguments)
    else:
        model = ConvLSTMNowcaster(**model_arguments)
    output_dir = repo_root / config["artifacts"]["model_dir"] / model_cfg["version"]
    loss = training["loss"]
    return train_model(
        model,
        loaders["train"],
        loaders["validation"],
        normalizer=normalizer,
        output_dir=output_dir,
        data_version=config["data"]["version"],
        model_version=model_cfg["version"],
        epochs=int(training["epochs"]),
        learning_rate=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        event_threshold_mm_h=float(loss.get("event_threshold_mm_h", 5.0)),
        event_weight=float(loss.get("event_weight", 4.0)),
        mse_weight=float(loss["mse_weight"]),
        intensity_thresholds_mm_h=loss.get("thresholds_mm_h"),
        intensity_weights=loss.get("weights"),
        validation_thresholds_mm_h=[
            float(value) for value in config["evaluation"]["thresholds_mm_h"]
        ],
        validation_score_config=training.get("validation_score"),
        sampling_metadata=sampling_metadata,
        gradient_clip_norm=float(training["gradient_clip_norm"]),
        early_stopping_patience=int(training["early_stopping_patience"]),
        scheduler_patience=int(training["scheduler"]["patience"]),
        scheduler_factor=float(training["scheduler"]["factor"]),
        device=device_override or str(training.get("device", "auto")),
        seed=int(training["seed"]),
        resume_from=resume_from,
    )
