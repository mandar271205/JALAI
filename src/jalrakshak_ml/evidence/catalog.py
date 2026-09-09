"""Flood event catalog with evidence-backed, explicit state transitions."""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class EventState(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    EVIDENCE_PARTIAL = "EVIDENCE_PARTIAL"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    BENCHMARK_ELIGIBLE = "BENCHMARK_ELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class FloodEvent:
    event_id: str
    start_time: str
    end_time: str
    state: EventState
    rainfall_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    flood_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    exposure_snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    vulnerability_snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    hydraulic_simulation_refs: tuple[str, ...] = field(default_factory=tuple)
    citizen_report_refs: tuple[str, ...] = field(default_factory=tuple)
    model_prediction_refs: tuple[str, ...] = field(default_factory=tuple)
    severity: str | None = None
    severity_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.event_id.startswith("mumbai_monsoon_"):
            raise ValueError("Event ID must use the Mumbai monsoon namespace")
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("Event requires ordered timezone-aware timestamps")
        evidence_refs = set(self.rainfall_evidence_refs) | set(self.flood_evidence_refs)
        if self.severity and not self.severity_evidence_refs:
            raise ValueError("Event severity cannot be asserted without cited evidence")
        if self.state is EventState.CANDIDATE and self.severity:
            raise ValueError("A candidate window cannot assert flood severity")
        if self.state in {EventState.EVIDENCE_VERIFIED, EventState.BENCHMARK_ELIGIBLE} and (
            not self.rainfall_evidence_refs or not self.flood_evidence_refs
        ):
            raise ValueError("Verified events require both rainfall and flood evidence")
        if self.state is EventState.BENCHMARK_ELIGIBLE and not (
            self.exposure_snapshot_refs and self.vulnerability_snapshot_refs
        ):
            raise ValueError("Benchmark eligibility requires exposure and vulnerability snapshots")
        if self.severity_evidence_refs and not set(self.severity_evidence_refs).issubset(
            evidence_refs
        ):
            raise ValueError("Severity evidence must be registered on the event")

    def transition(self, state: EventState, *, reason: str) -> FloodEvent:
        if not reason:
            raise ValueError("Event state transitions require an auditable reason")
        allowed = {
            EventState.CANDIDATE: {
                EventState.EVIDENCE_PARTIAL,
                EventState.INSUFFICIENT_EVIDENCE,
            },
            EventState.EVIDENCE_PARTIAL: {
                EventState.EVIDENCE_VERIFIED,
                EventState.INSUFFICIENT_EVIDENCE,
            },
            EventState.EVIDENCE_VERIFIED: {EventState.BENCHMARK_ELIGIBLE},
            EventState.BENCHMARK_ELIGIBLE: set(),
            EventState.INSUFFICIENT_EVIDENCE: {EventState.EVIDENCE_PARTIAL},
        }
        if state not in allowed[self.state]:
            raise ValueError(f"Unsafe event transition {self.state.value} -> {state.value}")
        updated = FloodEvent(**{**asdict(self), "state": state, "caveats": (*self.caveats, reason)})
        updated.validate()
        return updated

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


class EventCatalog:
    version = "mumbai_flood_event_catalog_v1"

    def __init__(self, events: list[FloodEvent]):
        if len({event.event_id for event in events}) != len(events):
            raise ValueError("Event IDs must be unique")
        for event in events:
            event.validate()
        self.events = tuple(events)

    def write_atomic(self, path: str | Path) -> dict[str, Any]:
        destination = Path(path)
        if destination.exists():
            raise FileExistsError("Flood event catalogs are immutable")
        body = {
            "catalog_version": self.version,
            "events": [event.to_dict() for event in self.events],
        }
        body["catalog_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + ".part")
        part.write_text(json.dumps(body, indent=2, allow_nan=False), encoding="utf-8")
        part.replace(destination)
        return body

    @classmethod
    def load(cls, path: str | Path) -> EventCatalog:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        claimed = payload.pop("catalog_sha256", None)
        if (
            claimed
            != hashlib.sha256(
                json.dumps(payload, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
        ):
            raise ValueError("Flood event catalog hash mismatch")
        if payload.get("catalog_version") != cls.version:
            raise ValueError("Flood event catalog version mismatch")
        events = []
        for item in payload["events"]:
            item["state"] = EventState(item["state"])
            for key in tuple(item):
                if key.endswith("_refs") or key == "caveats":
                    item[key] = tuple(item[key])
            events.append(FloodEvent(**item))
        return cls(events)
