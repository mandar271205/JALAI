"""Generate decision-ready explanations for flood risk without causal overclaiming."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.explain.risk_explanation import ExplainabilityEngine, format_risk_explanation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rainfall", type=float, default=45.0, help="Rainfall rate mm/h")
    parser.add_argument("--susceptibility", type=float, default=0.72, help="Susceptibility score [0, 1]")
    parser.add_argument("--exposure", type=float, default=0.65, help="Exposure score [0, 1]")
    parser.add_argument("--vulnerability", type=float, default=0.50, help="Vulnerability score [0, 1]")
    parser.add_argument("--risk-level", choices=["LOW", "MODERATE", "HIGH", "SEVERE"], default="HIGH")
    parser.add_argument("--output-json", type=Path, default=Path("reports/risk_explanation_sample.json"))
    args = parser.parse_args()

    explanation = ExplainabilityEngine.explain(
        risk_level=args.risk_level,
        rainfall_value=args.rainfall,
        susceptibility_value=args.susceptibility,
        exposure_value=args.exposure,
        vulnerability_value=args.vulnerability,
        uncertainty_info={"status": "MEASURED_ENSEMBLE", "spread_sd": 0.12, "calibrated": False},
        data_quality_info={"status": "PARTIAL_CENSUS", "elevation_quality": "HIGH_COP30"},
        limitations=[
            "Hydraulic calibration unavailable",
            "Socioeconomic vulnerability uses heuristic proxy",
        ],
        model_versions={"nowcast": "st_attention_v1", "risk": "hev_v1"},
        source_versions={"dem": "copernicus_glo_30", "rainfall": "gpm_imerg_v07"},
    )

    formatted_text = format_risk_explanation(explanation)
    print("\n--- HUMAN READABLE EXPLANATION ---")
    print(formatted_text)

    payload = explanation.to_dict()
    print("\n--- MACHINE READABLE PAYLOAD ---")
    print(json.dumps(payload, indent=2))

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved explanation to: {args.output_json}")


if __name__ == "__main__":
    main()
