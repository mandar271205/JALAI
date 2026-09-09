"""Create a fail-closed benchmark skeleton without opening locked data."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.research.benchmark import (
    BenchmarkMetric,
    MetricStatus,
    assemble_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/phase8_final_benchmark_skeleton.json")
    )
    parser.add_argument(
        "--results-json",
        type=Path,
        help="Optional JSON list of explicit evaluated metric records",
    )
    parser.add_argument("--locked-test", action="store_true", help="Forbidden in this Phase 8 task")
    args = parser.parse_args()
    if args.locked_test:
        parser.error(
            "locked-test access is forbidden; provide future approved result manifests instead"
        )
    provided = []
    if args.results_json:
        for row in json.loads(args.results_json.read_text(encoding="utf-8")):
            row["status"] = MetricStatus(row["status"])
            provided.append(BenchmarkMetric(**row))
    metrics = [row.to_dict() for row in assemble_benchmark(provided)]
    payload = {"locked_test_accessed": False, "metrics": metrics}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": len(metrics)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
