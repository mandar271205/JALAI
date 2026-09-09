"""Audit genuine drainage vector layers and export DrainageEvidenceManifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.flood.drainage import DrainageAuditor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--waterways-geojson",
        type=Path,
        default=Path("data/processed/static/waterways.geojson"),
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=Path("reports/phase7_drainage_evidence_manifest.json"),
    )
    args = parser.parse_args()

    auditor = DrainageAuditor(args.waterways_geojson)
    manifest = auditor.audit()

    manifest_dict = manifest.to_dict()
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest_dict, indent=2), encoding="utf-8")

    print(json.dumps(manifest_dict, indent=2))
    print(f"\nDrainage evidence manifest written to: {args.output_manifest}")


if __name__ == "__main__":
    main()
