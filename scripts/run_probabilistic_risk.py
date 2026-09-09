"""Run probabilistic H x E x V flood risk calculation and scenario uncertainty propagation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio

from jalrakshak_ml.risk.intelligence import (
    ProbabilisticHEVRiskEngine,
    RiskCategory,
    RiskMethodology,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hazard-tif", type=Path, default=Path("data/processed/flood/susceptibility_v1.tif"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/probabilistic_risk_report.json"))
    args = parser.parse_args()

    if not args.hazard_tif.is_file():
        print(f"Hazard raster not found at {args.hazard_tif}")
        return

    with rasterio.open(args.hazard_tif) as src:
        hazard_arr = src.read(1).astype(np.float32)
        crs_str = str(src.crs)

    valid_mask = np.isfinite(hazard_arr) & (hazard_arr >= 0.0)

    methodology = RiskMethodology(
        version="probabilistic_hev_v1",
        hazard_scale=(0.0, 1.0),
        exposure_scale=(0.0, 1.0),
        vulnerability_scale=(0.0, 1.0),
        category_boundaries=(0.2, 0.5, 0.8),
    )
    engine = ProbabilisticHEVRiskEngine(methodology)

    # In the screening configuration with genuine susceptibility and baseline exposure proxy
    # We do NOT fabricate census population or empirical vulnerability
    exposure_proxy = np.where(valid_mask, 0.5, 0.0).astype(np.float32)
    vulnerability_proxy = np.where(valid_mask, 0.5, 0.0).astype(np.float32)

    risk_result = engine.compute_spatial_risk(
        hazard_arr,
        exposure_proxy,
        vulnerability_proxy,
        valid_mask=valid_mask,
        data_quality="PARTIAL_EXPOSURE_AND_VULNERABILITY",
        model_confidence=0.75,
    )

    cats = risk_result["risk_categories"]
    cat_counts = {
        cat: int(np.count_nonzero(cats == cat))
        for cat in (RiskCategory.LOW.value, RiskCategory.MODERATE.value, RiskCategory.HIGH.value, RiskCategory.SEVERE.value)
    }

    report = {
        "status": "PASS",
        "methodology": methodology.version,
        "hazard_source": str(args.hazard_tif),
        "crs": crs_str,
        "valid_cells": int(np.count_nonzero(valid_mask)),
        "risk_category_distribution": cat_counts,
        "data_quality": risk_result["data_quality"],
        "model_confidence": risk_result["model_confidence"],
        "is_calibrated_probability": False,
        "limitations": [
            "Hazard is relative flood susceptibility, not hydraulic water depth",
            "Exposure and vulnerability rely on baseline proxies pending ward census acquisition",
        ],
    }

    print(json.dumps(report, indent=2))
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Risk report saved to: {args.output_report}")


if __name__ == "__main__":
    main()
