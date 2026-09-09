"""Evaluate Phase 8 scientific claims; strict mode fails on blocked requested claims."""

import argparse
import json

from jalrakshak_ml.research.claims import ClaimStatus, evaluate_all, evaluate_claim


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", action="append", help="Claim ID; omit to audit all")
    parser.add_argument(
        "--evidence", action="append", default=[], help="Present evidence capability"
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    decisions = (
        [evaluate_claim(item, set(args.evidence)) for item in args.claim]
        if args.claim
        else evaluate_all(set(args.evidence))
    )
    print(json.dumps([decision.to_dict() for decision in decisions], indent=2))
    return 2 if args.strict and any(d.status is ClaimStatus.BLOCKED for d in decisions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
