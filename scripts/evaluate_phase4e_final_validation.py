"""Evaluate precomputed, paired Phase 4E validation predictions; test data is rejected."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from jalrakshak_ml.deep_nowcast.final_evaluation import evaluate_validation_events
from jalrakshak_ml.deep_nowcast.phase4e_runner import event_block_bootstrap
from jalrakshak_ml.deep_nowcast.splits import VALIDATION_EVENTS_AUTHORITATIVE, is_locked_test_event


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction-manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(Path(args.prediction_manifest).read_text(encoding="utf-8"))
    if manifest.get("split") != "validation":
        raise PermissionError("Only validation predictions are accepted")
    records = manifest.get("events", [])
    if {record["event_id"] for record in records} != set(VALIDATION_EVENTS_AUTHORITATIVE):
        raise ValueError("Prediction manifest must contain exactly three validation events")
    if any(is_locked_test_event(record["event_id"]) for record in records):
        raise PermissionError("Locked test entered validation evaluator")
    event_data = {}
    for record in records:
        with np.load(record["artifact"], allow_pickle=False) as arrays:
            event_data[record["event_id"]] = (
                arrays["prediction_mm_h"],
                arrays["target_mm_h"],
                arrays["valid_mask"],
            )
    report = evaluate_validation_events(event_data)
    if args.bootstrap:
        report["event_bootstrap"] = event_block_bootstrap(
            {
                event_id: [values["horizons"]["30"]["continuous"]["mae"]]
                for event_id, values in report["per_event"].items()
            }
        )
    report["locked_test_accessed"] = False
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("Validation report already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    part.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(output)


if __name__ == "__main__":
    main()
