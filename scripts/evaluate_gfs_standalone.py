"""CLI to run standalone GFS benchmark evaluation on the 51 locked test samples."""
from __future__ import annotations

import argparse
import json

from jalrakshak_ml.gfs_replay.benchmark import evaluate_gfs_standalone


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate standalone GFS rainfall forecasts on held-out test set.")
    parser.add_argument(
        "--benchmark",
        default="data/processed/benchmarks/mumbai_locked_test_51_v1.json",
        help="Path to locked test benchmark manifest",
    )
    parser.add_argument(
        "--gfs-root",
        default="data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1",
        help="Path to GFS replay directory",
    )
    parser.add_argument(
        "--gpm-root",
        default="data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
        help="Path to GPM expanded dataset directory",
    )
    parser.add_argument(
        "--output-json",
        default="reports/phase4_gfs_standalone_evaluation.json",
        help="Path to output evaluation JSON",
    )
    parser.add_argument(
        "--output-report",
        default="reports/phase4_gfs_standalone_report.md",
        help="Path to output Markdown report",
    )
    args = parser.parse_args()

    report = evaluate_gfs_standalone(
        benchmark_manifest_path=args.benchmark,
        gfs_replay_root=args.gfs_root,
        gpm_dataset_dir=args.gpm_root,
        output_json_path=args.output_json,
        output_report_path=args.output_report,
    )
    print(f"Standalone GFS Evaluation complete:")
    print(f"Overall MAE: {report['overall']['mae']:.4f} mm/h")
    print(f"Overall RMSE: {report['overall']['rmse']:.4f} mm/h")
    print(f"Valid pixels: {report['cell_counts']['common_valid_cells']:,}")
    print(f"Report written to: {args.output_report}")
    print(f"JSON written to: {args.output_json}")


if __name__ == "__main__":
    main()
