"""CLI script to build the Phase 7 Physics Scenario Catalog and Simulation Size Plan.

Generates reproducible scenario definitions from historical rainfall events and static
geospatial layers, adhering strictly to locked test boundaries and empirical claim gates.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from jalrakshak_ml.flood.scenario_catalog import PhysicsScenarioBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Phase 7 physics simulation scenario catalog and size planning."
    )
    parser.add_argument(
        "--events-catalog",
        type=Path,
        default=Path("data/catalogs/mumbai_rainfall_events_v1.json"),
        help="Path to locked rainfall events catalog JSON",
    )
    parser.add_argument(
        "--elevation",
        type=Path,
        default=Path("data/processed/static/elevation.tif"),
        help="Path to canonical elevation GeoTIFF",
    )
    parser.add_argument(
        "--roughness",
        type=Path,
        default=Path("data/processed/static/roughness.tif"),
        help="Path to canonical surface roughness GeoTIFF",
    )
    parser.add_argument(
        "--output-catalog",
        type=Path,
        default=Path("reports/phase7_physics_scenario_catalog.json"),
        help="Path to output scenario catalog JSON",
    )
    args = parser.parse_args()

    builder = PhysicsScenarioBuilder(
        events_catalog_path=args.events_catalog,
        elevation_path=args.elevation,
        roughness_path=args.roughness,
    )
    report = builder.build_catalog()

    args.output_catalog.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_catalog, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)

    logger.info(f"Built physics scenario catalog with {report.total_scenarios} scenarios:")
    for split_name, count in report.scenarios_by_split.items():
        logger.info(f"  - Split '{split_name}': {count} scenarios")
    logger.info(f"Saved catalog to {args.output_catalog}")


if __name__ == "__main__":
    main()
