"""Unified forecast provider contracts and adapters for multi-model nowcasting & NWP fusion.

Standardises outputs across Persistence, pySTEPS, ConvLSTM V2, and GFS NWP.
Maintains backwards compatibility with NowcastResult.
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from jalrakshak_ml.nowcast.contracts import NowcastResult, build_result
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


def _ensure_utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(slots=True)
class ForecastResult:
    """Standardised result envelope for all forecast providers and fusion models."""

    rainfall_mm_h: np.ndarray
    horizons_min: list[int]
    issue_time: datetime
    valid_mask: np.ndarray
    provider: str
    model_version: str
    data_version: str
    source_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    native_cadence_minutes: int = 30
    output_cadence_minutes: int = 30
    confidence: np.ndarray | float | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    expected_rainfall_mm_h: np.ndarray | None = None
    exceedance_probabilities: dict[float, np.ndarray] | None = None
    probability_thresholds_mm_h: list[float] | None = None
    ensemble_spread: np.ndarray | None = None
    provider_disagreement: np.ndarray | None = None
    forecast_confidence: np.ndarray | float | None = None
    calibration_status: str | dict[str, str] | None = None
    calibration_version: str | None = None
    uncertainty_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rainfall_mm_h = np.asarray(self.rainfall_mm_h, dtype=np.float32)
        if self.rainfall_mm_h.ndim != 3:
            raise ValueError(f"rainfall_mm_h must have shape (horizon, y, x), got {self.rainfall_mm_h.shape}")
        h, y, x = self.rainfall_mm_h.shape
        if len(self.horizons_min) != h:
            raise ValueError(f"horizons_min count ({len(self.horizons_min)}) must match horizon dimension ({h})")
        if any(v <= 0 for v in self.horizons_min):
            raise ValueError("All horizons_min values must be positive integers")

        self.valid_mask = np.asarray(self.valid_mask, dtype=bool)
        if self.valid_mask.shape != self.rainfall_mm_h.shape:
            raise ValueError(
                f"valid_mask shape {self.valid_mask.shape} must match rainfall shape {self.rainfall_mm_h.shape}"
            )

        self.issue_time = _ensure_utc(self.issue_time)

        finite_vals = self.rainfall_mm_h[np.isfinite(self.rainfall_mm_h)]
        if finite_vals.size and np.any(finite_vals < 0):
            raise ValueError("rainfall_mm_h contains negative values, which is physically invalid")

        if self.expected_rainfall_mm_h is None:
            self.expected_rainfall_mm_h = self.rainfall_mm_h
        else:
            self.expected_rainfall_mm_h = np.asarray(self.expected_rainfall_mm_h, dtype=np.float32)
            if self.expected_rainfall_mm_h.shape != (h, y, x):
                raise ValueError(
                    f"expected_rainfall_mm_h shape {self.expected_rainfall_mm_h.shape} must match ({h}, {y}, {x})"
                )

        if self.exceedance_probabilities is not None:
            for thr, prob in self.exceedance_probabilities.items():
                prob_arr = np.asarray(prob, dtype=np.float32)
                if prob_arr.shape != (h, y, x):
                    raise ValueError(
                        f"exceedance_probabilities[{thr}] shape {prob_arr.shape} must match ({h}, {y}, {x})"
                    )
                finite_p = prob_arr[np.isfinite(prob_arr)]
                if finite_p.size and (np.any(finite_p < -1e-5) or np.any(finite_p > 1.0 + 1e-5)):
                    raise ValueError(f"exceedance_probabilities[{thr}] contains values outside valid [0, 1] range")

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable metadata manifest."""
        return {
            "provider": self.provider,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "issue_time": self.issue_time.isoformat(),
            "horizons_min": list(self.horizons_min),
            "units": "mm/h",
            "shape": list(self.rainfall_mm_h.shape),
            "native_cadence_minutes": self.native_cadence_minutes,
            "output_cadence_minutes": self.output_cadence_minutes,
            "source_metadata": self.source_metadata,
            "provenance": self.provenance,
            "uncertainty": self.uncertainty,
            "probability_thresholds_mm_h": self.probability_thresholds_mm_h,
            "calibration_status": self.calibration_status,
            "calibration_version": self.calibration_version,
            "forecast_type": "probabilistic" if self.exceedance_probabilities is not None else ("deterministic" if not self.uncertainty else "hybrid_probabilistic_scaffold"),
        }

    def to_nowcast_result(self) -> NowcastResult:
        """Convert to canonical NowcastResult for backwards compatibility."""
        return build_result(
            self.rainfall_mm_h,
            issue_time=self.issue_time,
            provider=self.provider,
            model_version=self.model_version,
            data_version=self.data_version,
            temporal_step_minutes=self.output_cadence_minutes,
            source_metadata={
                **self.source_metadata,
                "provenance": self.provenance,
                "native_cadence_minutes": self.native_cadence_minutes,
                "uncertainty": self.uncertainty,
            },
        )


class BaseForecastProvider(abc.ABC):
    """Abstract base contract for radar, deep-learning, NWP, and fusion providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider unique identifier."""

    @property
    @abc.abstractmethod
    def model_version(self) -> str:
        """Model or algorithm version."""

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        """True if dependencies and data/checkpoints are ready for inference."""

    @abc.abstractmethod
    def predict(
        self,
        *,
        history_frames: np.ndarray,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        """Generate standardised forecast result."""


class PersistenceProvider(BaseForecastProvider):
    """Operational lag-0 baseline provider."""

    def __init__(self, data_version: str = "operational_v1") -> None:
        self._core = PersistenceNowcast()
        self._data_version = data_version

    @property
    def name(self) -> str:
        return "persistence"

    @property
    def model_version(self) -> str:
        return "persistence_lag0_v1"

    @property
    def is_available(self) -> bool:
        return True

    def predict(
        self,
        *,
        history_frames: np.ndarray,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        issue_time = _ensure_utc(issue_time)
        latest_frame = history_frames[-1]
        preds = self._core.predict(latest_frame, lead_times=lead_times)
        valid_mask = np.isfinite(preds)
        horizons = [temporal_step_minutes * (i + 1) for i in range(lead_times)]
        return ForecastResult(
            rainfall_mm_h=preds,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=valid_mask,
            provider=self.name,
            model_version=self.model_version,
            data_version=self._data_version,
            source_metadata={"event_id": event_id},
            provenance={"method": "persistence_repeat_latest_frame"},
            native_cadence_minutes=temporal_step_minutes,
            output_cadence_minutes=temporal_step_minutes,
        )


class PystepsProvider(BaseForecastProvider):
    """Operational optical-flow nowcaster provider."""

    def __init__(self, data_version: str = "operational_v1") -> None:
        self._core = PystepsNowcast()
        self._data_version = data_version

    @property
    def name(self) -> str:
        return "pysteps"

    @property
    def model_version(self) -> str:
        return "pysteps_lucaskanade_extrapolation_v1"

    @property
    def is_available(self) -> bool:
        return self._core._is_available

    def predict(
        self,
        *,
        history_frames: np.ndarray,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        issue_time = _ensure_utc(issue_time)
        preds = self._core.predict(history_frames, lead_times=lead_times)
        valid_mask = np.isfinite(preds)
        horizons = [temporal_step_minutes * (i + 1) for i in range(lead_times)]
        return ForecastResult(
            rainfall_mm_h=preds,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=valid_mask,
            provider=self.name,
            model_version=self.model_version,
            data_version=self._data_version,
            source_metadata={
                "event_id": event_id,
                "pysteps_available": self._core._is_available,
                "fallback_to_persistence": bool(not self._core._is_available and self._core.fallback),
            },
            provenance={"method": "pysteps_optical_flow" if self._core._is_available else "persistence_fallback"},
            native_cadence_minutes=temporal_step_minutes,
            output_cadence_minutes=temporal_step_minutes,
        )


class ConvLSTMProvider(BaseForecastProvider):
    """Experimental deep-learning nowcaster provider (ConvLSTM V2)."""

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        data_version: str = "gpm_imerg_v07_mumbai_monsoon_expanded_v1",
        device: str = "auto",
    ) -> None:
        self._checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self._data_version = data_version
        self._device = device
        self._inference = None
        if self._checkpoint_path and self._checkpoint_path.exists():
            try:
                from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
                self._inference = ConvLSTMInference(self._checkpoint_path, device=device)
            except Exception:
                self._inference = None

    @property
    def name(self) -> str:
        return "convlstm_v2"

    @property
    def model_version(self) -> str:
        return "convlstm_mumbai_heavyrain_v2"

    @property
    def is_available(self) -> bool:
        return self._inference is not None

    def predict(
        self,
        *,
        history_frames: np.ndarray,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        issue_time = _ensure_utc(issue_time)
        horizons = [temporal_step_minutes * (i + 1) for i in range(lead_times)]
        if not self.is_available:
            raise RuntimeError(
                f"ConvLSTMProvider is not available (checkpoint {self._checkpoint_path} missing or unvalidated). "
                "Operational fallback or missing-provider policy must be invoked by caller."
            )
        preds = self._inference.predict(history_frames, lead_times=lead_times)
        valid_mask = np.isfinite(preds)
        return ForecastResult(
            rainfall_mm_h=preds,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=valid_mask,
            provider=self.name,
            model_version=self.model_version,
            data_version=self._data_version,
            source_metadata={
                "event_id": event_id,
                "checkpoint_path": str(self._checkpoint_path),
                "checkpoint_hash": getattr(self._inference, "checkpoint_hash", None),
            },
            provenance={"method": "convlstm_v2_forward_inference"},
            native_cadence_minutes=temporal_step_minutes,
            output_cadence_minutes=temporal_step_minutes,
        )


class GFSReplayProvider(BaseForecastProvider):
    """Verified Phase-4A GFS NWP replay provider with strict as-of anti-leakage checks."""

    def __init__(
        self,
        replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1",
        latency_hours: int = 6,
    ) -> None:
        self.replay_root = Path(replay_root)
        self.latency_hours = latency_hours
        self._manifest: dict[str, Any] | None = None
        self._sample_index: dict[tuple[str, str], dict[str, Any]] = {}
        if self.replay_root.exists():
            manifest_file = self.replay_root / "manifest.json"
            if manifest_file.exists():
                self._manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                for record in self._manifest.get("samples", []):
                    key = (str(record["event_id"]), _ensure_utc(record["issue_time"]).isoformat())
                    self._sample_index[key] = record

    @property
    def name(self) -> str:
        return "gfs"

    @property
    def model_version(self) -> str:
        return "gfs_quarter_degree_replay_v1"

    @property
    def is_available(self) -> bool:
        return bool(self._sample_index)

    def predict(
        self,
        *,
        history_frames: np.ndarray | None = None,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        issue_time = _ensure_utc(issue_time)
        if not event_id:
            raise ValueError("GFSReplayProvider requires event_id to look up replay sample")
        key = (event_id, issue_time.isoformat())
        if key not in self._sample_index:
            raise KeyError(
                f"No verified GFS replay sample for event_id={event_id!r}, issue_time={issue_time.isoformat()}"
            )
        sample_meta = self._sample_index[key]
        sample_dir = self.replay_root / sample_meta["path"]
        array_path = sample_dir / "rainfall.npz"
        meta_path = sample_dir / "metadata.json"
        if not array_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"Missing GFS replay artifacts in {sample_dir}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        avail_time = _ensure_utc(meta["availability_time"])
        if avail_time > issue_time:
            raise ValueError(
                f"Anti-leakage violation: GFS availability time {avail_time.isoformat()} is after "
                f"issue time {issue_time.isoformat()}"
            )

        with np.load(array_path, allow_pickle=False) as arrays:
            rates = arrays["rainfall_rate_mm_h"][:lead_times]

        valid_mask = np.isfinite(rates)
        horizons = [temporal_step_minutes * (i + 1) for i in range(rates.shape[0])]
        forecast_age_hours = (issue_time - _ensure_utc(meta["cycle_time"])).total_seconds() / 3600.0

        return ForecastResult(
            rainfall_mm_h=rates,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=valid_mask,
            provider=self.name,
            model_version=self.model_version,
            data_version=str(self._manifest.get("data_version", "gfs_mumbai_locked_test_replay_v1")),
            source_metadata={
                "event_id": event_id,
                "cycle_time": meta["cycle_time"],
                "availability_time": meta["availability_time"],
                "forecast_age_hours": forecast_age_hours,
                "latency_hours": self.latency_hours,
                "source_variable": "prate_avg",
                "api_crs": meta.get("api_crs", "EPSG:4326"),
                "canonical_crs": meta.get("spatial", {}).get("target_grid", {}).get("crs", "EPSG:32643"),
            },
            provenance={
                "temporal_disaggregation": meta.get("temporal_disaggregation_method", "uniform_within_native_interval"),
                "array_sha256": sample_meta.get("array_sha256"),
            },
            native_cadence_minutes=int(meta.get("native_cadence_minutes", 60)),
            output_cadence_minutes=int(meta.get("output_cadence_minutes", 30)),
        )
