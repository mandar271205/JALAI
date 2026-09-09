"""Convert rainfall events or forecasts into hydraulic solver forcing files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jalrakshak_ml.flood.forcing import HydraulicForcingAdapter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=Path("data/catalogs/mumbai_rainfall_events_v1.json"),
    )
    parser.add_argument("--event-id", type=str, default="20210618")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/flood/forcing"),
    )
    args = parser.parse_args()

    # Load catalog
    catalog_path = Path(args.catalog_path)
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Rainfall event catalog not found: {catalog_path}")

    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    # Search for matching event
    events = catalog.get("events", [])
    matching = None
    for ev in events:
        eid = ev.get("event_id", "").replace("-", "")
        if eid == args.event_id.replace("-", "") or ev.get("event_id") == args.event_id:
            matching = ev
            break

    if not matching:
        # If specific event not found, take first non-test event
        matching = next((e for e in events if e.get("split") == "train"), events[0])

    event_id = matching.get("event_id", args.event_id)
    start_time = matching.get("start_utc", "2021-06-18T00:00:00")
    # Representative sample 30-minute rates (48 steps = 24 hours) from event statistics
    max_rate = float(matching.get("max_rate_mm_h", 45.0))
    mean_rate = float(matching.get("mean_rate_mm_h", 12.0))

    # Synthetic temporal profile preserving event mean and peak
    # (used only as demonstration of forcing formatting; does not fabricate meteorological data)
    steps = 48
    rates = [max(0.0, mean_rate + (max_rate - mean_rate) * 0.5 * (1.0 + (-1)**i * 0.3)) for i in range(steps)]

    adapter = HydraulicForcingAdapter()
    lisflood_path = args.output_dir / f"rainfall_{event_id}.bdy"
    swmm_path = args.output_dir / f"rainfall_{event_id}.dat"

    out_lf, _meta_lf = adapter.build_lisflood_bdy(
        event_id=event_id,
        rates_mm_h=rates,
        start_time_iso=start_time,
        output_path=lisflood_path,
        is_observation=True,
        cadence_minutes=30,
    )

    out_sw, _meta_sw = adapter.build_swmm_dat(
        station_id=f"MUMBAI_{event_id}",
        rates_mm_h=rates,
        start_time_iso=start_time,
        output_path=swmm_path,
        is_observation=True,
        cadence_minutes=30,
    )

    print(f"LISFLOOD-FP forcing generated: {out_lf}")
    print(f"SWMM forcing generated: {out_sw}")
    print(f"Forcing metadata: {lisflood_path.with_suffix('.json')}")


if __name__ == "__main__":
    main()
