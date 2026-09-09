"""Safe serialization adapters for existing internal endpoints."""

from __future__ import annotations

import enum
from typing import Any


class ServingState(str, enum.Enum):
    UNAVAILABLE = "UNAVAILABLE"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNVALIDATED = "UNVALIDATED"
    CALIBRATED = "CALIBRATED"
    FROZEN = "FROZEN"


def serialize_internal_response(
    endpoint: str,
    *,
    state: ServingState,
    payload: dict[str, Any] | None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    allowed = {
        "/internal/v1/nowcast",
        "/internal/v1/inundation",
        "/internal/v1/risk",
        "/internal/v1/report-verification",
        "/internal/v1/models/status",
        "/internal/v1/runs/{run_id}",
    }
    if endpoint not in allowed:
        raise ValueError("Unsupported internal endpoint")
    if state is ServingState.UNAVAILABLE and payload:
        raise ValueError("Unavailable responses cannot contain scientific predictions")
    if endpoint == "/internal/v1/nowcast" and payload:
        if payload.get("units") != "mm/h":
            raise ValueError("Nowcast API rainfall units must be mm/h")
        if payload.get("crs") != "EPSG:4326":
            raise ValueError("Nowcast API CRS must be EPSG:4326")
    if (
        endpoint == "/internal/v1/inundation"
        and payload
        and "water_depth" in payload
        and state not in {ServingState.CALIBRATED, ServingState.FROZEN}
    ):
        raise ValueError("Water depth cannot be serialized from unvalidated physics")
    return {
        "endpoint": endpoint,
        "state": state.value,
        "data": payload,
        "evidence_refs": evidence_refs or [],
        "scientific_status_explicit": True,
    }
