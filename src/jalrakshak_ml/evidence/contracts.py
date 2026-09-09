"""Typed historical evidence records with strict quantity semantics."""

from __future__ import annotations

import enum
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EvidenceType(str, enum.Enum):
    OBSERVED_SENSOR = "OBSERVED_SENSOR"
    OFFICIAL_REPORTED = "OFFICIAL_REPORTED"
    CITIZEN_REPORTED = "CITIZEN_REPORTED"
    REMOTE_SENSING_DERIVED = "REMOTE_SENSING_DERIVED"
    NEWS_REPORTED = "NEWS_REPORTED"
    PHYSICS_SIMULATED = "PHYSICS_SIMULATED"
    MODEL_PREDICTED = "MODEL_PREDICTED"
    SUSCEPTIBILITY_ONLY = "SUSCEPTIBILITY_ONLY"
    UNKNOWN = "UNKNOWN"


class QuantityType(str, enum.Enum):
    RAIN_RATE = "RAIN_RATE"
    RAIN_ACCUMULATION = "RAIN_ACCUMULATION"
    WATER_DEPTH = "WATER_DEPTH"
    FLOOD_EXTENT = "FLOOD_EXTENT"
    ROAD_CLOSURE = "ROAD_CLOSURE"
    BUILDING_IMPACT = "BUILDING_IMPACT"
    REPORT_LOCATION = "REPORT_LOCATION"
    SUSCEPTIBILITY_SCORE = "SUSCEPTIBILITY_SCORE"
    UNKNOWN = "UNKNOWN"


class VerificationState(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PARTIAL = "PARTIAL"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    event_id: str
    start_time: str
    end_time: str
    geometry: dict[str, Any] | None
    spatial_reference: str | None
    source: str
    source_reference: str | None
    source_organization: str
    evidence_type: EvidenceType
    quantity_type: QuantityType
    value: Any
    units: str
    crs: str
    spatial_resolution: str | None
    temporal_resolution: str | None
    confidence: float | None
    quality_score: float
    verification_state: VerificationState
    provenance: dict[str, Any]
    checksum: str
    created_at: str
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not all(
            (
                self.evidence_id,
                self.event_id,
                self.source,
                self.source_organization,
                self.units,
                self.crs,
                self.provenance,
            )
        ):
            raise ValueError("Evidence identity, source, units, CRS, and provenance are required")
        if _parse_time(self.end_time) < _parse_time(self.start_time):
            raise ValueError("Evidence end_time precedes start_time")
        _parse_time(self.created_at)
        if not _HEX64.fullmatch(self.checksum):
            raise ValueError("Evidence checksum must be a lowercase SHA-256")
        if not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("Evidence quality score must be in [0,1]")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Evidence confidence must be in [0,1]")
        if self.evidence_type is EvidenceType.SUSCEPTIBILITY_ONLY:
            if self.quantity_type is not QuantityType.SUSCEPTIBILITY_SCORE:
                raise ValueError("Susceptibility evidence cannot be depth or observed extent")
            if self.units not in {"dimensionless", "score_0_1"}:
                raise ValueError("Susceptibility scores must be dimensionless")
        if self.quantity_type is QuantityType.SUSCEPTIBILITY_SCORE and self.evidence_type not in {
            EvidenceType.SUSCEPTIBILITY_ONLY,
            EvidenceType.MODEL_PREDICTED,
        }:
            raise ValueError(
                "Susceptibility quantity requires an explicit model-only evidence type"
            )
        if self.quantity_type is QuantityType.WATER_DEPTH and self.evidence_type not in {
            EvidenceType.OBSERVED_SENSOR,
            EvidenceType.OFFICIAL_REPORTED,
            EvidenceType.PHYSICS_SIMULATED,
            EvidenceType.MODEL_PREDICTED,
        }:
            raise ValueError("Water depth requires sensor, official, physics, or model provenance")
        if self.verification_state is VerificationState.VERIFIED and self.evidence_type in {
            EvidenceType.CITIZEN_REPORTED,
            EvidenceType.NEWS_REPORTED,
            EvidenceType.UNKNOWN,
        }:
            raise ValueError("Uncorroborated report classes cannot be promoted to verified truth")

    def require_quantity(self, expected: QuantityType) -> EvidenceRecord:
        self.validate()
        if self.quantity_type is not expected:
            raise TypeError(
                f"Evidence {self.evidence_id} is {self.quantity_type.value}, not {expected.value}"
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["evidence_type"] = self.evidence_type.value
        payload["quantity_type"] = self.quantity_type.value
        payload["verification_state"] = self.verification_state.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceRecord:
        data = dict(payload)
        data["evidence_type"] = EvidenceType(data["evidence_type"])
        data["quantity_type"] = QuantityType(data["quantity_type"])
        data["verification_state"] = VerificationState(data["verification_state"])
        data["caveats"] = tuple(data.get("caveats", ()))
        record = cls(**data)
        record.validate()
        return record


class EvidenceRegistry:
    version = "historical_flood_evidence_v1"

    def __init__(self, records: list[EvidenceRecord]):
        if len({record.evidence_id for record in records}) != len(records):
            raise ValueError("Evidence IDs must be unique")
        for record in records:
            record.validate()
        self.records = tuple(records)

    def query(
        self,
        *,
        event_id: str | None = None,
        quantity_type: QuantityType | None = None,
    ) -> list[EvidenceRecord]:
        return [
            record
            for record in self.records
            if (event_id is None or record.event_id == event_id)
            and (quantity_type is None or record.quantity_type is quantity_type)
        ]

    def payload(self) -> dict[str, Any]:
        body = {
            "registry_version": self.version,
            "created_at": datetime.now(UTC).isoformat(),
            "records": [record.to_dict() for record in self.records],
            "susceptibility_usable_as_depth": False,
            "susceptibility_usable_as_observed_extent": False,
        }
        canonical = json.dumps(body, sort_keys=True, allow_nan=False).encode()
        return {**body, "registry_sha256": hashlib.sha256(canonical).hexdigest()}

    def write_atomic(self, path: str | Path) -> dict[str, Any]:
        destination = Path(path)
        if destination.exists():
            raise FileExistsError("Evidence registries are immutable")
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.payload()
        part = destination.with_suffix(destination.suffix + ".part")
        part.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
        part.replace(destination)
        return payload

    @classmethod
    def load(cls, path: str | Path) -> EvidenceRegistry:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        claimed = payload.pop("registry_sha256", None)
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        if claimed != actual or payload.get("registry_version") != cls.version:
            raise ValueError("Evidence registry hash/version mismatch")
        return cls([EvidenceRecord.from_dict(item) for item in payload["records"]])
