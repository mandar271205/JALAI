"""Train or resume the configured Phase-3 ConvLSTM."""
from __future__ import annotations

import argparse

from jalrakshak_ml.deep_nowcast.train import train_from_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/training/convlstm_mumbai_v1.yaml")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--resume", default=None, help="Path to latest.pt or another compatible checkpoint")
    args = parser.parse_args()
    outcome = train_from_config(args.config, device_override=args.device, resume_from=args.resume)
    print(f"Best checkpoint: {outcome.best_checkpoint}")
    print(f"SHA-256: {outcome.checkpoint_hash}")
    print(f"Best validation loss: {outcome.best_validation_loss:.6f}")
    print(f"Best validation score: {outcome.best_validation_score:.6f}")
    print(f"Best epoch: {outcome.best_epoch}")
    print(f"Device: {outcome.device}")


if __name__ == "__main__":
    main()
