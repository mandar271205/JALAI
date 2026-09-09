"""Verify citizen flood reports against environmental evidence without claiming AI verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.citizen.verification import CitizenReport, CitizenReportVerificationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-id", type=str, default="rep_mumbai_001")
    parser.add_argument("--text", type=str, default="Severe waterlogging on Hindmata flyover below bridge, knee-deep")
    parser.add_argument("--lat", type=float, default=19.01)
    parser.add_argument("--lon", type=float, default=72.84)
    parser.add_argument("--timestamp", type=str, default="2024-07-21T12:00:00+00:00")
    parser.add_argument("--rainfall-rate", type=float, default=38.5, help="Local rainfall rate mm/h")
    parser.add_argument("--susceptibility", type=float, default=0.82, help="Local susceptibility score [0, 1]")
    parser.add_argument("--nearby-count", type=int, default=3, help="Corroborating reports nearby")
    parser.add_argument("--output-json", type=Path, default=Path("reports/citizen_report_verification_sample.json"))
    args = parser.parse_args()

    report = CitizenReport(
        report_id=args.report_id,
        timestamp=args.timestamp,
        latitude=args.lat,
        longitude=args.lon,
        text_description=args.text,
        image_metadata={"format": "jpeg", "has_exif": True},
    )

    engine = CitizenReportVerificationEngine()
    result = engine.verify_report(
        report,
        local_rainfall_rate_mm_h=args.rainfall_rate,
        local_susceptibility_score=args.susceptibility,
        nearby_reports_count=args.nearby_count,
    )

    out = result.to_dict()
    print(json.dumps(out, indent=2))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nVerification result saved to: {args.output_json}")


if __name__ == "__main__":
    main()
