"""Evaluate Persistence, pySTEPS, and ConvLSTM on the same held-out events."""
from __future__ import annotations

import argparse
import json

from jalrakshak_ml.deep_nowcast.evaluate import evaluate_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/training/convlstm_mumbai_v1.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()
    report = evaluate_from_config(args.config, checkpoint_path=args.checkpoint, device=args.device)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
