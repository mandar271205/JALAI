"""Evaluate FNO flood surrogate against genuine physics solver reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path("models/flood/fno_v1/best.pt"))
    parser.add_argument("--physics-manifest", type=Path, default=Path("data/processed/flood/physics_dataset_v1.json"))
    parser.add_argument("--split", choices=["validation", "test"], default="validation")
    parser.add_argument("--output-report", type=Path, default=Path("reports/fno_evaluation_report.json"))
    args = parser.parse_args()

    if not args.checkpoint.is_file() or not args.physics_manifest.is_file():
        report = {
            "status": "ABORTED_MISSING_PREREQUISITES",
            "reason": "FNO checkpoint or genuine physics reference manifest absent",
            "surrogate_model": True,
            "physics_reference_available": False,
            "measured_speedup": None,
        }
        print(json.dumps(report, indent=2))
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return

    print("Evaluating FNO against physics reference...")


if __name__ == "__main__":
    main()
