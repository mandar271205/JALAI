"""Provider-neutral rainfall-nowcast result contract.

The Phase-2 providers continue to expose their lightweight ``predict`` methods.
``predict_result`` wraps those arrays in this common contract so callers do not
need provider-specific response handling when ConvLSTM is selected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


@dataclass(slots=True)
class NowcastResult:
    """Canonical deterministic nowcast plus auditable provenance metadata."""

    rainfall: np.ndarray
    issue_time: datetime
    horizons_min: list[int]
    provider: str
    model_version: str
    data_version: str
    source_metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_hash: str | None = None
    prediction_artifact_uri: str | None = None

    def __post_init__(self) -> None:
        self.rainfall = np.asarray(self.rainfall, dtype=np.float32)
        if self.rainfall.ndim != 3:
            raise ValueError("rainfall must have shape [horizon, height, width]")
        if self.rainfall.shape[0] != len(self.horizons_min):
            raise ValueError("horizons_min must match the rainfall horizon dimension")
        if any(h <= 0 for h in self.horizons_min):
            raise ValueError("horizons_min values must be positive")
        finite = self.rainfall[np.isfinite(self.rainfall)]
        if finite.size and np.any(finite < 0):
            raise ValueError("rainfall predictions must be non-negative")

    def to_manifest(self) -> dict[str, Any]:
        """Return the JSON-safe metadata envelope (the raster stays external)."""
        return {
            "provider": self.provider,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "issue_time": _utc_iso(self.issue_time),
            "horizons_min": list(self.horizons_min),
            "units": "mm/h",
            "shape": list(self.rainfall.shape),
            "source_metadata": self.source_metadata,
            "checkpoint_hash": self.checkpoint_hash,
            "prediction_artifact_uri": self.prediction_artifact_uri,
            "forecast_type": "deterministic",
        }

    def save(self, output_dir: str | Path, stem: str = "nowcast") -> tuple[Path, Path]:
        """Persist predictions and their manifest, then return both paths."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        array_path = output_dir / f"{stem}.npz"
        np.savez_compressed(array_path, rainfall=self.rainfall)
        self.prediction_artifact_uri = str(array_path.resolve())
        manifest_path = output_dir / f"{stem}.json"
        manifest_path.write_text(
            json.dumps(self.to_manifest(), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        return array_path, manifest_path


def build_result(
    rainfall: np.ndarray,
    *,
    issue_time: datetime,
    provider: str,
    model_version: str,
    data_version: str,
    temporal_step_minutes: int = 30,
    source_metadata: dict[str, Any] | None = None,
    checkpoint_hash: str | None = None,
) -> NowcastResult:
    """Build the common result envelope for any deterministic provider."""
    rainfall = np.asarray(rainfall, dtype=np.float32)
    horizons = [temporal_step_minutes * (i + 1) for i in range(rainfall.shape[0])]
    return NowcastResult(
        rainfall=rainfall,
        issue_time=issue_time,
        horizons_min=horizons,
        provider=provider,
        model_version=model_version,
        data_version=data_version,
        source_metadata=source_metadata or {},
        checkpoint_hash=checkpoint_hash,
    )
