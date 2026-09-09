"""Freeze the validation-selected Phase 4E winner without opening locked test data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.deep_nowcast.phase4e_prepare import freeze_winner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--prerequisites", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("MODEL_SELECTION_FROZEN=false")
        print("LOCKED_TEST_TOUCHED=false")
        return
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    prerequisites = json.loads(Path(args.prerequisites).read_text(encoding="utf-8"))
    manifest = freeze_winner(selection, prerequisites, args.output)
    print(json.dumps(manifest, indent=2, allow_nan=False))
    print("LOCKED_TEST_TOUCHED=false")


if __name__ == "__main__":
    main()
