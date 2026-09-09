"""Inspect genuine-label readiness and optionally train the citizen baseline."""

import argparse
import json

from jalrakshak_ml.citizen.baseline import inspect_training_readiness, train_classical_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument(
        "--train", action="store_true", help="Train only when genuine readiness gates pass"
    )
    args = parser.parse_args()
    result = (
        train_classical_baseline(args.manifest)
        if args.train
        else inspect_training_readiness(args.manifest)
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
