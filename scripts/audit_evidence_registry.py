"""Validate and materialize an immutable Phase 8 evidence registry."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.evidence.contracts import EvidenceRecord, EvidenceRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", help="JSON list of evidence records")
    parser.add_argument("output_json", help="New immutable registry path")
    args = parser.parse_args()
    rows = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    payload = EvidenceRegistry([EvidenceRecord.from_dict(row) for row in rows]).write_atomic(
        args.output_json
    )
    print(json.dumps({"ready": True, "registry_sha256": payload["registry_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
