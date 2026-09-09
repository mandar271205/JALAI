"""Separate future locked-test gate; this preparation build never evaluates test data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--winner-manifest", required=True)
    parser.add_argument("--test-config", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    winner_path, test_config = Path(args.winner_manifest), Path(args.test_config)
    if not winner_path.is_file() or not test_config.is_file():
        raise FileNotFoundError("Valid winner freeze and explicit test config are both required")
    winner = json.loads(winner_path.read_text(encoding="utf-8"))
    if (
        winner.get("MODEL_SELECTION_FROZEN") is not True
        or winner.get("locked_test_accessed") is not False
        or winner.get("locked_test_automatically_run") is not False
    ):
        raise PermissionError("Winner manifest does not authorize one final test evaluation")
    if not args.execute:
        print("LOCKED_TEST_TOUCHED=false")
        return
    raise RuntimeError(
        "Locked-test evaluator is deliberately absent from this preparation commit; "
        "add it only after winner freeze and independent review"
    )


if __name__ == "__main__":
    main()
