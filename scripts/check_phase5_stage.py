"""Fail-closed prerequisite gate for future Phase 5 execution stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STAGES = (
    "susceptibility-build",
    "susceptibility-audit",
    "physics-scenario-prepare",
    "solver-environment-smoke",
    "one-genuine-physics-scenario",
    "physics-output-audit",
    "multi-scenario-generation",
    "physics-dataset-freeze",
    "fno-normalization",
    "fno-gpu-smoke",
    "fno-training",
    "heldout-physics-comparison",
    "exposure-build",
    "vulnerability-build",
    "hev-risk",
    "uncertainty-propagation",
    "explainability",
)


def _passed(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("status") in {"PASS", "COMPLETE", "FROZEN", "SUCCESS"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    missing = [path for path in map(Path, args.require) if not path.is_file() or not _passed(path)]
    if missing:
        raise RuntimeError(f"Phase 5 stage gate closed; missing/pending: {missing}")
    result = {
        "stage": args.stage,
        "prerequisites_passed": True,
        "execution_requested": args.execute,
        "scientific_execution_performed": False,
        "message": "Gate passed; invoke the stage-specific engine with genuine inputs.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
