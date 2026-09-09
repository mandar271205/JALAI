"""Check SWMM model readiness, blockers, and municipal data acquisition checklist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.flood.solver_readiness import audit_swmm_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drainage-path", type=Path, default=None)
    parser.add_argument("--solver-cmd", type=str, default="swmm5")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("reports/phase7_swmm_readiness_report.json"),
    )
    args = parser.parse_args()

    report = audit_swmm_readiness(drainage_path=args.drainage_path, solver_cmd=args.solver_cmd)
    report_dict = report.to_dict()

    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    print(json.dumps(report_dict, indent=2))
    print(f"\nSWMM readiness report saved to: {args.output_report}")
    print(f"SWMM_INPUTS_AVAILABLE: {report.swmm_inputs_available}")
    print(f"SWMM_EXECUTION_READY: {report.executable_input_ready}")


if __name__ == "__main__":
    main()
