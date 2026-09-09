"""Classify source freshness with observed/assumed availability provenance."""

import argparse
import json

from jalrakshak_ml.research.freshness import classify_freshness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_id")
    parser.add_argument("reference_time")
    parser.add_argument("--observation-time")
    parser.add_argument("--cadence-minutes", type=float)
    parser.add_argument("--availability-time")
    parser.add_argument(
        "--availability-basis", choices=["OBSERVED", "ASSUMED", "UNKNOWN"], default="UNKNOWN"
    )
    args = parser.parse_args()
    result = classify_freshness(
        args.source_id,
        reference_time=args.reference_time,
        observation_time=args.observation_time,
        expected_cadence_minutes=args.cadence_minutes,
        availability_timestamp=args.availability_time,
        availability_basis=args.availability_basis,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
