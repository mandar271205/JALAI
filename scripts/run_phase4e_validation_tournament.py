"""Prepare the Phase 4E GPU validation tournament; execution stays explicitly gated."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.deep_nowcast.phase4e_prepare import tournament_execution_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/phase4e_validation_tournament_plan.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = tournament_execution_plan()
    Path(args.output).write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if args.execute:
        raise RuntimeError(
            "Execution gate closed: run download/replay/channel audits and train-only normalization first; "
            "then instantiate ValidationOnlyRunner with audited datasets."
        )
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
