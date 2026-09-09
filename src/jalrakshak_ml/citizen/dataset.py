"""Leakage-resistant citizen-report dataset manifest builder."""

from __future__ import annotations

import enum
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class CitizenLabel(str, enum.Enum):
    GENUINE_SUPPORTED = "GENUINE_SUPPORTED"
    GENUINE_UNCERTAIN = "GENUINE_UNCERTAIN"
    LIKELY_SPAM = "LIKELY_SPAM"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LabeledCitizenSample:
    report_id: str
    event_id: str
    timestamp: str
    text: str
    structured_features: dict[str, float | int | None]
    label: CitizenLabel
    label_source: str
    label_provenance: dict[str, Any]
    duplicate_group_id: str | None = None
    image_embedding_reference: str | None = None

    def validate(self) -> None:
        if not self.report_id or not self.event_id or not self.label_source:
            raise ValueError("Explicit report, event, and label source are required")
        if not self.label_provenance or self.label_provenance.get("method") in {
            "heuristic",
            "pseudo_label",
            "model_prediction",
        }:
            raise ValueError("Pseudo-labels cannot be used as genuine labels")


class CitizenDatasetBuilder:
    version = "citizen_labeled_dataset_v1"

    def build(
        self,
        samples: list[LabeledCitizenSample],
        event_splits: dict[str, str],
        destination: str | Path,
    ) -> dict[str, Any]:
        if not samples:
            raise ValueError("No explicitly labeled samples supplied")
        report_ids: set[str] = set()
        duplicate_splits: dict[str, str] = {}
        rows: list[dict[str, Any]] = []
        for sample in samples:
            sample.validate()
            if sample.report_id in report_ids:
                raise ValueError("Duplicate report_id")
            report_ids.add(sample.report_id)
            split = event_splits.get(sample.event_id)
            if split not in {"train", "validation", "test"}:
                raise ValueError("Every event must have an explicit event-level split")
            if sample.duplicate_group_id:
                previous = duplicate_splits.setdefault(sample.duplicate_group_id, split)
                if previous != split:
                    raise ValueError("Duplicate reports cannot cross dataset splits")
            row = asdict(sample)
            row["label"] = sample.label.value
            row["split"] = split
            row["supervised_eligible"] = sample.label is not CitizenLabel.UNKNOWN
            rows.append(row)
        body = {
            "dataset_version": self.version,
            "split_strategy": "event_level_explicit",
            "samples": rows,
            "class_balance": dict(Counter(row["label"] for row in rows)),
            "unknown_used_for_supervised_training": False,
            "input_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
        }
        body["manifest_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        path = Path(destination)
        if path.exists():
            raise FileExistsError("Citizen dataset manifests are immutable")
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        part.write_text(json.dumps(body, indent=2, allow_nan=False), encoding="utf-8")
        part.replace(path)
        return body
