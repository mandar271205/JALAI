"""Calibrate skill-derived fusion weights using TRAIN and VALIDATION events only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.deep_nowcast.dataset import build_datasets_from_config
from jalrakshak_ml.fusion.calibration import calibrate_skill_weights


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate skill-derived fusion weights on train/val data.")
    parser.add_argument(
        "--config",
        default="configs/training/convlstm_mumbai_expanded_v1.yaml",
        help="Training dataset config with train, validation, and test events",
    )
    parser.add_argument(
        "--output-weights",
        default="configs/fusion/weights_v1.yaml",
        help="Output path for calibrated weights YAML",
    )
    args = parser.parse_args()

    datasets, normalizer = build_datasets_from_config(args.config)
    train_ds = datasets["train"]
    val_ds = datasets["validation"]
    print(f"Calibration using TRAIN events: {train_ds.event_ids} ({len(train_ds)} samples)")
    print(f"Calibration using VALIDATION events: {val_ds.event_ids} ({len(val_ds)} samples)")

    manifest = calibrate_skill_weights(
        train_ds,
        val_ds,
        output_weights_path=args.output_weights,
    )
    print(f"\nCalibration complete! Weights written to {args.output_weights}:")
    print(json.dumps(manifest["weights_by_horizon"], indent=2))


if __name__ == "__main__":
    main()
