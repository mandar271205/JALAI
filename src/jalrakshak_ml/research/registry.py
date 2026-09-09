"""Hash-addressed model, data, and evidence lifecycle registry."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .common import atomic_immutable_json, canonical_hash


class Lifecycle(str, enum.Enum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION_CANDIDATE = "VALIDATION_CANDIDATE"
    FROZEN = "FROZEN"
    LOCKED_TEST_EVALUATED = "LOCKED_TEST_EVALUATED"
    REJECTED = "REJECTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class RegistryRecord:
    artifact_id: str
    artifact_kind: str
    lifecycle: Lifecycle
    model_version: str | None
    data_version: str | None
    evidence_version: str | None
    config_hash: str
    git_sha: str
    normalization_hash: str | None
    training_dataset_hash: str | None
    physics_dataset_hash: str | None
    source_versions: dict[str, str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.artifact_id or self.artifact_kind not in {"model", "data", "evidence"}:
            raise ValueError("Valid artifact identity and kind required")
        if self.lifecycle is Lifecycle.FROZEN and self.metadata.get("phase4e_unfinished", False):
            raise ValueError("unfinished Phase 4E models cannot be marked FROZEN")
        if self.lifecycle in {
            Lifecycle.FROZEN,
            Lifecycle.LOCKED_TEST_EVALUATED,
        } and not self.metadata.get("freeze_manifest_hash"):
            raise ValueError("Frozen lifecycle requires an immutable freeze manifest hash")


class ArtifactRegistry:
    def __init__(self, records: list[RegistryRecord]):
        if len({r.artifact_id for r in records}) != len(records):
            raise ValueError("Artifact IDs must be unique")
        for record in records:
            record.validate()
        self.records = tuple(records)

    def write(self, path: str | Path) -> dict[str, Any]:
        rows = []
        for record in self.records:
            row = asdict(record)
            row["lifecycle"] = record.lifecycle.value
            rows.append(row)
        body = {"registry_version": "model_data_evidence_registry_v1", "records": rows}
        body["registry_sha256"] = canonical_hash(body)
        return atomic_immutable_json(path, body)
