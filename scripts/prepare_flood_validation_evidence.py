"""Audit historical flood validation evidence and export FloodValidationManifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.flood.validation_evidence import FloodEvidenceIngestor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flood-dir",
        type=Path,
        default=Path("data/processed/flood"),
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=Path("reports/phase7_flood_validation_manifest.json"),
    )
    args = parser.parse_args()

    ingestor = FloodEvidenceIngestor(search_dir=args.flood_dir)
    manifest = ingestor.audit_evidence_availability()
    manifest_dict = manifest.to_dict()

    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest_dict, indent=2), encoding="utf-8")

    print(json.dumps(manifest_dict, indent=2))
    print(f"\nFlood validation manifest written to: {args.output_manifest}")
    print(f"REAL_FLOOD_VALIDATION_DATA_AVAILABLE: {manifest.real_flood_validation_data_available}")


if __name__ == "__main__":
    main()
