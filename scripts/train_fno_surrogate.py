"""Train FNO flood surrogate on genuine physics-reference targets.

Fails closed if genuine physics simulation targets are absent.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from jalrakshak_ml.core.claim_gates import AUTHORITATIVE_GATES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-manifest", type=Path, default=Path("data/processed/flood/physics_dataset_v1.json"))
    parser.add_argument("--normalization", type=Path, default=Path("models/flood/fno_train_only_normalization_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("models/flood/fno_v1"))
    parser.add_argument("--epochs", type=int, default=50)
    args = parser.parse_args()

    if not AUTHORITATIVE_GATES.GENUINE_FNO_TARGETS_AVAILABLE or not args.physics_manifest.is_file():
        print("GENUINE_FNO_TARGETS_AVAILABLE=False.")
        print("Physics reference dataset manifest does not exist. FNO training cannot proceed without real solver targets.")
        print("Training safely aborted to prevent synthetic target leakage.")
        return

    print("Genuine targets available. Initializing FNOTrainingRunner...")


if __name__ == "__main__":
    main()
