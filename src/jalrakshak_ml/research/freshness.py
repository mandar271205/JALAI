"""Source freshness classification with explicit publication-time provenance."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


class FreshnessState(str, enum.Enum):
    FRESH = "FRESH"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessResult:
    source_id: str
    state: FreshnessState
    age_minutes: float | None
    expected_cadence_minutes: float | None
    availability_timestamp: str | None
    availability_basis: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["state"] = self.state.value
        return row


def classify_freshness(
    source_id: str,
    *,
    reference_time: str,
    observation_time: str | None,
    expected_cadence_minutes: float | None,
    availability_timestamp: str | None = None,
    availability_basis: str = "UNKNOWN",
) -> FreshnessResult:
    if availability_basis not in {"OBSERVED", "ASSUMED", "UNKNOWN"}:
        raise ValueError("availability_basis must be OBSERVED, ASSUMED, or UNKNOWN")
    if availability_basis == "OBSERVED" and availability_timestamp is None:
        raise ValueError("Observed publication availability requires its timestamp")
    if observation_time is None:
        return FreshnessResult(
            source_id,
            FreshnessState.UNAVAILABLE,
            None,
            expected_cadence_minutes,
            availability_timestamp,
            availability_basis,
            ("observation/issue time unavailable",),
        )
    if expected_cadence_minutes is None or expected_cadence_minutes <= 0:
        return FreshnessResult(
            source_id,
            FreshnessState.UNKNOWN,
            None,
            expected_cadence_minutes,
            availability_timestamp,
            availability_basis,
            ("expected cadence unavailable",),
        )
    now = datetime.fromisoformat(reference_time)
    observed = datetime.fromisoformat(observation_time)
    if now.tzinfo is None or observed.tzinfo is None:
        raise ValueError("Freshness timestamps must include timezone")
    if availability_timestamp is not None:
        availability = datetime.fromisoformat(availability_timestamp)
        if availability.tzinfo is None:
            raise ValueError("Availability timestamp must include timezone")
    age = (now - observed).total_seconds() / 60
    if age < 0:
        state = FreshnessState.UNKNOWN
        reasons = ("source timestamp is later than reference time",)
    elif age <= expected_cadence_minutes * 1.5:
        state = FreshnessState.FRESH
        reasons = ("age within 1.5 expected cadences",)
    elif age <= expected_cadence_minutes * 3:
        state = FreshnessState.DEGRADED
        reasons = ("age exceeds normal cadence",)
    else:
        state = FreshnessState.STALE
        reasons = ("age exceeds three expected cadences",)
    if availability_basis == "ASSUMED":
        reasons += ("publication availability is assumed, not observed",)
    return FreshnessResult(
        source_id,
        state,
        age,
        expected_cadence_minutes,
        availability_timestamp,
        availability_basis,
        reasons,
    )
