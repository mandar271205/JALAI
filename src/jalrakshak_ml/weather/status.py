"""Source Availability, Data Quality, and Model Confidence Framework.

Enforces strict separation between:
1. Availability (is data accessible without temporal leakage?)
2. Data Quality (is physical observation sane, valid, and uncorrupted?)
3. Model Confidence (what is the predictive certainty of the downstream forecast?)

These concepts are NEVER merged into a single metric.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from jalrakshak_ml.weather.registry import WEATHER_SOURCE_REGISTRY, SourceRegistryEntry


@dataclass(slots=True)
class WeatherSourceStatus:
    """Standardized availability and data health descriptor for a weather source."""

    source_id: str
    source_name: str
    status: str
    available: bool
    last_available_time: datetime | None
    age_minutes: float | None
    quality_score: float | None
    missing_fraction: float | None
    latency_estimate_minutes: int
    native_resolution: str
    native_cadence_minutes: int
    reason_codes: list[str]
    eligibility_mode: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "status": self.status,
            "available": self.available,
            "last_available_time": (
                self.last_available_time.isoformat() if self.last_available_time else None
            ),
            "age_minutes": round(self.age_minutes, 1) if self.age_minutes is not None else None,
            "quality_score": (
                round(self.quality_score, 4) if self.quality_score is not None else None
            ),
            "missing_fraction": (
                round(self.missing_fraction, 4) if self.missing_fraction is not None else None
            ),
            "latency_estimate_minutes": self.latency_estimate_minutes,
            "native_resolution": self.native_resolution,
            "native_cadence_minutes": self.native_cadence_minutes,
            "reason_codes": list(self.reason_codes),
            "eligibility_mode": self.eligibility_mode,
            "provenance": self.provenance,
        }


def get_source_status_snapshot(
    issue_time: datetime | str,
    active_observations: dict[str, Any] | None = None,
) -> dict[str, WeatherSourceStatus]:
    """Compile comprehensive status snapshot of all weather sources as of issue_time."""
    ref_time = (
        datetime.fromisoformat(issue_time).replace(tzinfo=UTC)
        if isinstance(issue_time, str)
        else issue_time
    )
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=UTC)

    obs = active_observations or {}
    snapshot: dict[str, WeatherSourceStatus] = {}

    for src_id, entry in WEATHER_SOURCE_REGISTRY.items():
        if src_id in obs:
            obs_info = obs[src_id]
            last_time = obs_info.get("last_available_time")
            age = (ref_time - last_time).total_seconds() / 60.0 if last_time else None
            q_score = obs_info.get("quality_score", 1.0)
            missing = obs_info.get("missing_fraction", 0.0)
            reasons = obs_info.get("reason_codes", ["ACTIVE_OBSERVATION_STREAM"])
            status = "AVAILABLE"
            available = True
        else:
            last_time = None
            age = None
            q_score = None
            missing = None
            status = entry.live_status
            available = status == "READY"
            reasons = [f"DEFAULT_STATUS_{status}"]
            if status == "AUTH_REQUIRED":
                reasons.append("CREDENTIALS_OR_MOU_REQUIRED")
            elif status == "ARCHIVE_ONLY":
                reasons.append("HISTORICAL_GROUND_TRUTH_ONLY")

        snapshot[src_id] = WeatherSourceStatus(
            source_id=src_id,
            source_name=entry.source_name,
            status=status,
            available=available,
            last_available_time=last_time,
            age_minutes=age,
            quality_score=q_score,
            missing_fraction=missing,
            latency_estimate_minutes=entry.expected_latency_minutes,
            native_resolution=entry.spatial_resolution,
            native_cadence_minutes=entry.cadence_minutes,
            reason_codes=reasons,
            eligibility_mode=entry.eligibility_mode,
        )

    return snapshot
