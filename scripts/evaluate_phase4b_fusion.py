"""CLI to evaluate multi-model fusion benchmarks on the 51 locked held-out test samples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.fusion.benchmark import evaluate_phase4b_fusion


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate multi-model nowcast fusion on held-out test set.")
    parser.add_argument(
        "--benchmark",
        default="data/processed/benchmarks/mumbai_locked_test_51_v1.json",
        help="Path to locked test benchmark manifest",
    )
    parser.add_argument(
        "--gpm-root",
        default="data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
        help="Path to GPM expanded dataset directory",
    )
    parser.add_argument(
        "--gfs-root",
        default="data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1",
        help="Path to GFS replay directory",
    )
    parser.add_argument(
        "--weights",
        default="configs/fusion/weights_v1.yaml",
        help="Path to calibrated fusion weights",
    )
    parser.add_argument(
        "--output-json",
        default="reports/phase4_fusion_evaluation.json",
        help="Path to output evaluation JSON",
    )
    parser.add_argument(
        "--output-report",
        default="reports/phase4_fusion_foundation_report.md",
        help="Path to output Markdown report",
    )
    args = parser.parse_args()

    report = evaluate_phase4b_fusion(
        benchmark_manifest_path=args.benchmark,
        gpm_dataset_dir=args.gpm_root,
        gfs_replay_root=args.gfs_root,
        calibrated_weights_path=args.weights,
        output_json_path=args.output_json,
        output_report_path=args.output_report,
    )

    print("\nPhase 4B Multi-Model Fusion Evaluation Complete!")
    print(f"Total test samples evaluated: {report['total_samples']}")
    print(f"Common valid pixels evaluated: {report['common_valid_cells']:,}")
    print("\nOverall Performance:")
    for model_name, m_data in report["models"].items():
        mae = m_data["overall"]["mae"]
        rmse = m_data["overall"]["rmse"]
        print(f"  {model_name:22s} | MAE: {mae:.4f} mm/h | RMSE: {rmse:.4f} mm/h")

    sel = report["primary_selection"]
    print(f"\nOperational Nowcaster: {sel['operational_nowcaster']}")
    print(f"Operational Fusion:    {sel['operational_fusion_provider']}")
    print(f"Evaluation report written to: {args.output_report}")
    print(f"Evaluation JSON written to:   {args.output_json}")


if __name__ == "__main__":
    main()
