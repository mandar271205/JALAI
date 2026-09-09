"""Check LISFLOOD-FP surface-flow model readiness, input data, and solver availability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.flood.solver_readiness import audit_lisflood_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dem-path",
        type=Path,
        default=Path("data/processed/static/elevation.tif"),
    )
    parser.add_argument(
        "--roughness-path",
        type=Path,
        default=Path("data/processed/static/roughness.tif"),
    )
    parser.add_argument("--solver-cmd", type=str, default="lisflood")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("reports/phase7_lisflood_readiness_report.json"),
    )
    args = parser.parse_args()

    report = audit_lisflood_readiness(
        dem_path=args.dem_path,
        roughness_path=args.roughness_path,
        solver_cmd=args.solver_cmd,
    )
    report_dict = report.to_dict()

    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    print(json.dumps(report_dict, indent=2))
    print(f"\nLISFLOOD-FP readiness report saved to: {args.output_report}")
    print(f"LISFLOOD_INPUT_DATA_READY: {report.input_data_ready}")
    print(f"LISFLOOD_SOLVER_AVAILABLE: {report.solver_available}")
    print(f"LISFLOOD_EXECUTION_READY: {report.execution_ready}")


if __name__ == "__main__":
    main()
