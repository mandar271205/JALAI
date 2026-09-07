"""Plan or execute bounded Phase-3 IMERG data acquisition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.deep_nowcast.acquisition import HistoricalDataAcquirer, write_data_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/training/convlstm_mumbai_v1.yaml")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform downloads. Without this flag the command is a read-only dry run.",
    )
    args = parser.parse_args()
    acquirer = HistoricalDataAcquirer(args.config)
    result = acquirer.run(execute=args.execute)
    print(json.dumps(result, indent=2, default=str))
    if args.execute and result["status"] == "COMPLETE":
        report_path = Path(args.config).resolve().parents[2] / "reports" / "phase3_data_report.md"
        write_data_report(result["audit"], report_path)
        print(f"Data report: {report_path}")


if __name__ == "__main__":
    main()
