"""Fourier Neural Operator scaffold for genuine physics-reference flood depth."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


class SpectralConv2d(nn.Module):
    def __init__(self, channels: int, modes: int) -> None:
        super().__init__()
        self.channels = channels
        self.modes = modes
        scale = 1 / max(1, channels * channels)
        self.weight = nn.Parameter(
            scale * torch.randn(channels, channels, modes, modes, dtype=torch.cfloat)
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        transformed = torch.fft.rfft2(values)
        output = torch.zeros_like(transformed)
        modes_y = min(self.modes, transformed.shape[-2])
        modes_x = min(self.modes, transformed.shape[-1])
        output[:, :, :modes_y, :modes_x] = torch.einsum(
            "bixy,ioxy->boxy",
            transformed[:, :, :modes_y, :modes_x],
            self.weight[:, :, :modes_y, :modes_x],
        )
        return torch.fft.irfft2(output, s=values.shape[-2:])


class FloodFNO(nn.Module):
    """Compact surrogate that predicts four physics-depth horizons in metres."""

    model_version = "flood_fno_v1"
    surrogate_model = True

    def __init__(
        self,
        input_channels: int,
        *,
        width: int = 32,
        modes: int = 12,
        output_horizons: int = 4,
    ) -> None:
        super().__init__()
        if min(input_channels, width, modes, output_horizons) < 1:
            raise ValueError("FNO dimensions must be positive")
        self.input_channels = input_channels
        self.output_horizons = output_horizons
        self.lift = nn.Conv2d(input_channels, width, 1)
        self.spectral = nn.ModuleList([SpectralConv2d(width, modes) for _ in range(4)])
        self.local = nn.ModuleList([nn.Conv2d(width, width, 1) for _ in range(4)])
        self.project = nn.Sequential(
            nn.Conv2d(width, width, 1), nn.GELU(), nn.Conv2d(width, output_horizons, 1)
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        if inputs.ndim != 4 or inputs.shape[1] != self.input_channels:
            raise ValueError("FNO inputs must have shape [B,C,H,W]")
        if not torch.isfinite(inputs).all():
            raise ValueError("FNO input contains NaN or Inf")
        values = self.lift(inputs)
        for spectral, local in zip(self.spectral, self.local, strict=True):
            values = F.gelu(spectral(values) + local(values))
        # Differentiable nonnegative depth. No upper clipping is imposed.
        depth = F.softplus(self.project(values), beta=5.0)
        return depth[:, :, None]


@dataclass(frozen=True)
class FNOTrainOnlyNormalization:
    """Audited train-scenario-only input normalization for the future FNO run."""

    path: Path
    sha256: str
    channel_order: tuple[str, ...]
    means: tuple[float, ...]
    standard_deviations: tuple[float, ...]

    @classmethod
    def load(cls, path: str | Path, physics_manifest: dict[str, Any]) -> FNOTrainOnlyNormalization:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        train_ids = {
            record["scenario_id"]
            for record in physics_manifest["records"]
            if record["split"] == "train"
        }
        if (
            payload.get("normalization_version") != "phase5_fno_train_only_v1"
            or payload.get("status") != "PASS"
            or payload.get("fitted_split") != "train"
            or set(payload.get("fitted_scenario_ids", ())) != train_ids
            or payload.get("validation_opened") is not False
            or payload.get("test_opened") is not False
        ):
            raise PermissionError("FNO normalization is not an audited train-only artifact")
        channels = tuple(payload.get("channel_order", ()))
        statistics = payload.get("input_statistics", {})
        if not channels or list(statistics) != list(channels):
            raise ValueError("FNO normalization channel order/statistics mismatch")
        means = tuple(float(statistics[channel]["mean"]) for channel in channels)
        stds = tuple(float(statistics[channel]["std"]) for channel in channels)
        if not np.isfinite([*means, *stds]).all() or any(value <= 0 for value in stds):
            raise ValueError("FNO normalization statistics are malformed")
        return cls(
            source,
            hashlib.sha256(source.read_bytes()).hexdigest(),
            channels,
            means,
            stds,
        )

    def normalize_inputs(self, values: torch.Tensor) -> torch.Tensor:
        if values.ndim != 4 or values.shape[1] != len(self.channel_order):
            raise ValueError("FNO input channels do not match normalization order")
        mean = values.new_tensor(self.means)[None, :, None, None]
        std = values.new_tensor(self.standard_deviations)[None, :, None, None]
        output = (values - mean) / std
        if not torch.isfinite(output).all():
            raise ValueError("FNO normalization produced NaN or Inf")
        return output


@dataclass(frozen=True)
class FNOTrainingConfig:
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    use_amp: bool = True
    monitored_metric: str = "validation.depth_mae_m"


class FNOTrainingRunner:
    """Training-step/checkpoint interface gated by genuine physics-reference provenance."""

    def __init__(
        self,
        physics_manifest_path: str | Path,
        normalization_path: str | Path,
        *,
        config: FNOTrainingConfig,
        git_commit: str,
    ) -> None:
        self.physics_manifest_path = Path(physics_manifest_path)
        self.physics_manifest = require_physics_reference_dataset(self.physics_manifest_path)
        self.normalization = FNOTrainOnlyNormalization.load(
            normalization_path, self.physics_manifest
        )
        self.config = config
        self.git_commit = git_commit

    def training_step(
        self,
        model: FloodFNO,
        inputs: torch.Tensor,
        reference_depth_m: torch.Tensor,
        valid_mask: torch.Tensor,
    ) -> torch.Tensor:
        prediction = model(self.normalization.normalize_inputs(inputs))
        if prediction.shape != reference_depth_m.shape or valid_mask.shape != prediction.shape:
            raise ValueError("FNO target and valid mask must match four-horizon model output")
        valid = valid_mask.bool() & torch.isfinite(reference_depth_m)
        if not torch.any(valid) or (reference_depth_m[valid] < 0).any():
            raise ValueError("FNO physics target must contain valid nonnegative depth in metres")
        return torch.nn.functional.smooth_l1_loss(prediction[valid], reference_depth_m[valid])

    def checkpoint_payload(
        self,
        model: FloodFNO,
        optimizer: torch.optim.Optimizer,
        *,
        epoch: int,
        validation_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        if epoch < 1 or not validation_metrics or any("test" in key for key in validation_metrics):
            raise ValueError("FNO checkpoints require validation-only evidence")
        return {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "epoch": epoch,
            "validation_metrics": validation_metrics,
            "model_version": model.model_version,
            "model_config": {
                "input_channels": model.input_channels,
                "output_horizons": model.output_horizons,
            },
            "runner_config": asdict(self.config),
            "physics_dataset_manifest_sha256": hashlib.sha256(
                self.physics_manifest_path.read_bytes()
            ).hexdigest(),
            "normalization_sha256": self.normalization.sha256,
            "git_commit": self.git_commit,
            "surrogate_model": True,
            "physics_reference": True,
            "locked_rainfall_test_accessed": False,
        }

    @staticmethod
    def save_checkpoint_atomic(payload: dict[str, Any], destination: str | Path) -> None:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        torch.save(payload, part)
        part.replace(path)


def require_physics_reference_dataset(manifest_path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    records = manifest.get("records", [])
    if (
        manifest.get("status") != "FROZEN"
        or not manifest.get("physics_reference")
        or manifest.get("target_quantity") != "physics_simulated_water_depth"
        or not records
        or any(not record.get("physically_simulated") for record in records)
        or any(not record.get("physics_reference") for record in records)
    ):
        raise PermissionError("FNO training requires a frozen genuine physics-reference corpus")
    scenario_ids = [record.get("scenario_id") for record in records]
    if len(scenario_ids) != len(set(scenario_ids)) or set(
        record.get("split") for record in records
    ) - {
        "train",
        "validation",
        "test",
    }:
        raise ValueError("Physics-reference scenarios/splits are malformed")
    claimed_hash = manifest.get("manifest_content_sha256")
    canonical = {key: value for key, value in manifest.items() if key != "manifest_content_sha256"}
    actual_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if claimed_hash != actual_hash:
        raise ValueError("Physics-reference manifest content hash mismatch")
    return manifest


def evaluate_fno(
    predicted_depth_m: np.ndarray,
    reference_depth_m: np.ndarray,
    valid_mask: np.ndarray,
    *,
    runtime_seconds: float | None = None,
    reference_runtime_seconds: float | None = None,
) -> dict[str, Any]:
    if (
        predicted_depth_m.shape != reference_depth_m.shape
        or valid_mask.shape != reference_depth_m.shape
    ):
        raise ValueError("FNO evaluation arrays must share shape")
    valid = (
        valid_mask.astype(bool) & np.isfinite(predicted_depth_m) & np.isfinite(reference_depth_m)
    )
    predicted, reference = predicted_depth_m[valid], reference_depth_m[valid]
    if not predicted.size:
        raise ValueError("FNO evaluation has no valid cells")
    threshold = 0.05
    intersection = np.count_nonzero((predicted >= threshold) & (reference >= threshold))
    union = np.count_nonzero((predicted >= threshold) | (reference >= threshold))
    report: dict[str, Any] = {
        "depth_mae_m": float(np.mean(np.abs(predicted - reference))),
        "depth_rmse_m": float(np.sqrt(np.mean((predicted - reference) ** 2))),
        "inundation_iou": float(intersection / union) if union else None,
        "inundation_csi": float(intersection / union) if union else None,
        "peak_depth_error_m": float(predicted.max() - reference.max()),
        "spatial_extent_error_cells": int(
            np.count_nonzero(predicted >= threshold) - np.count_nonzero(reference >= threshold)
        ),
        "surrogate_model": True,
        "physics_reference": True,
    }
    if runtime_seconds is not None:
        report["runtime_seconds"] = runtime_seconds
    if runtime_seconds and reference_runtime_seconds:
        report["measured_speedup"] = reference_runtime_seconds / runtime_seconds
    else:
        report["measured_speedup"] = None
    return report
