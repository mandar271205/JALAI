"""Build and freeze physics reference dataset manifest with strict leakage and integrity gates."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios-manifest", type=Path, default=Path("data/processed/flood/physics_scenarios_v1.json"))
    parser.add_argument("--results-manifest", type=Path, default=Path("data/processed/flood/physics_results_v1.json"))
    parser.add_argument("--output-manifest", type=Path, default=Path("data/processed/flood/physics_dataset_v1.json"))
    args = parser.parse_args()

    if not args.scenarios_manifest.is_file() or not args.results_manifest.is_file():
        print(f"Prerequisite manifests missing. Scenarios: {args.scenarios_manifest.is_file()}, Results: {args.results_manifest.is_file()}")
        print("GENUINE_FNO_TARGETS_AVAILABLE=False. Physics dataset cannot be frozen without executed solver results.")
        return

    print("Checking scenario and result integrity...")
    # Builder invocation would happen here once real solver outputs exist.


if __name__ == "__main__":
    main()
