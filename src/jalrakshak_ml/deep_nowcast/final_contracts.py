"""Fail-closed contracts for the final Phase 4E rainfall tournament."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.nn import functional as F

from .splits import (
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    is_locked_test_event,
)

OBS_CHANNEL_ORDER = ("rainfall_gpm",)
NWP_CHANNEL_ORDER = (
    "gfs_precipitation",
    "gfs_u10",
    "gfs_v10",
    "gfs_wind_speed",
    "gfs_wind_direction_sin",
    "gfs_wind_direction_cos",
    "gfs_t2m",
    "gfs_rh2m",
    "gfs_surface_pressure",
    "gfs_cape",
    "gfs_pwat",
)
STATIC_CHANNEL_ORDER = ("static_elevation",)
HORIZONS_MINUTES = (30, 60, 90, 120)
SEEDS = (26071, 26072, 26073)
GRID_CRS = "EPSG:32643"
GRID_SHAPE = (256, 256)
CROP_SHAPE = (128, 128)


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _shape(name: str, value: torch.Tensor, expected: tuple[int | None, ...]) -> None:
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if value.ndim != len(expected):
        raise ValueError(f"{name} must have rank {len(expected)}, got {tuple(value.shape)}")
    for actual, required in zip(value.shape, expected, strict=True):
        if required is not None and actual != required:
            raise ValueError(f"{name} expected shape {expected}, got {tuple(value.shape)}")


def validate_separated_inputs(
    obs_history: torch.Tensor,
    nwp_future: torch.Tensor,
    static_features: torch.Tensor,
    persistence_baseline: torch.Tensor | None = None,
) -> None:
    """Validate the non-negotiable final tensor contract without broadcasting."""
    _shape("obs_history", obs_history, (None, 4, 1, None, None))
    batch, _, _, height, width = obs_history.shape
    _shape("nwp_future", nwp_future, (batch, 4, 11, height, width))
    _shape("static_features", static_features, (batch, 1, height, width))
    if persistence_baseline is not None:
        _shape("persistence_baseline", persistence_baseline, (batch, 1, height, width))
    for name, tensor in (
        ("obs_history", obs_history),
        ("nwp_future", nwp_future),
        ("static_features", static_features),
    ):
        if not torch.isfinite(tensor).all():
            raise ValueError(f"{name} contains NaN or Inf")


def differentiable_nonnegative(value: torch.Tensor) -> torch.Tensor:
    """Map unconstrained rainfall to nonnegative mm/h with a low-floor smooth head.

    Beta 20 keeps the zero-logit floor (~0.035 mm/h) below the lowest 0.1 mm/h
    verification threshold while retaining differentiability and avoiding an upper clip.
    """
    return F.softplus(value, beta=20.0)


@dataclass(frozen=True, slots=True)
class FinalNormalization:
    """Verified, immutable view of a train-only Phase 4E normalization artifact."""

    path: Path
    sha256: str
    artifact: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path, *, expected_sha256: str | None = None) -> FinalNormalization:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"Final normalization artifact missing: {source}")
        digest = sha256_file(source)
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("Normalization artifact SHA-256 mismatch")
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("normalization_version") != "phase4e_train_only_v1":
            raise ValueError("Legacy or unknown normalization artifact rejected")
        if data.get("status") != "PASS" or data.get("audit_passed") is not True:
            raise ValueError("Normalization artifact did not pass its audit")
        if data.get("fitted_split") != "train":
            raise ValueError("Normalization was not fitted on train only")
        fitted_events = tuple(data.get("fitted_event_ids", ()))
        if set(fitted_events) != set(TRAIN_EVENTS_AUTHORITATIVE):
            raise ValueError("Normalization must contain exactly 12 authoritative train events")
        if any(
            is_locked_test_event(event) or event in VALIDATION_EVENTS_AUTHORITATIVE
            for event in fitted_events
        ):
            raise PermissionError("Normalization contains validation/test leakage")
        if (
            data.get("validation_opened") is not False
            or data.get("locked_test_opened") is not False
        ):
            raise ValueError("Normalization provenance indicates validation/test access")
        required_order = {
            "obs_history": list(OBS_CHANNEL_ORDER),
            "nwp_future": list(NWP_CHANNEL_ORDER),
            "static_features": list(STATIC_CHANNEL_ORDER),
        }
        if data.get("channel_order") != required_order:
            raise ValueError("Normalization channel order mismatch")
        statistics = data.get("statistics", {})
        for group, channels in required_order.items():
            group_stats = statistics.get(group, {})
            if list(group_stats) != channels:
                raise ValueError(f"Normalization statistics mismatch for {group}")
            for channel in channels:
                stat = group_stats[channel]
                if not np.isfinite([stat.get("mean"), stat.get("std")]).all() or stat["std"] <= 0:
                    raise ValueError(f"Malformed normalization statistics for {channel}")
        return cls(source, digest, data)

    def normalize(self, values: np.ndarray, *, group: str, channel: str) -> np.ndarray:
        stat = self.artifact["statistics"][group][channel]
        output = (np.asarray(values, dtype=np.float32) - float(stat["mean"])) / float(stat["std"])
        if not np.isfinite(output).all():
            raise ValueError(f"Normalization produced non-finite values for {channel}")
        return output.astype(np.float32, copy=False)
