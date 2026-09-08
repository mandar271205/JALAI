"""Read-only validation of all published Phase 4A arrays against the locked schedule."""

import argparse
import json
from pathlib import Path

import numpy as np

from jalrakshak_ml.gfs_replay.core import (
    HourlyInterval,
    allocate_half_hours,
    select_gfs_forecast_as_of,
    utc,
)
from jalrakshak_ml.gfs_replay.pipeline import sha256


def verify(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    benchmark_path = Path(manifest["benchmark_manifest"])
    assert sha256(benchmark_path) == manifest["benchmark_sha256"]
    benchmark = json.loads(benchmark_path.read_text())
    expected = {
        (e["event_id"], s["issue_time"]): s for e in benchmark["events"] for s in e["samples"]
    }
    assert len(expected) == manifest["sample_count"] == 51
    seen, grid = set(), None
    low, high, count = float("inf"), 0.0, 0
    for record in manifest["samples"]:
        key = record["event_id"], record["issue_time"]
        assert key in expected and key not in seen
        seen.add(key)
        folder = root / record["path"]
        metadata = json.loads((folder / "metadata.json").read_text())
        assert metadata["benchmark_sha256"] == manifest["benchmark_sha256"]
        assert sha256(folder / "rainfall.npz") == record["array_sha256"] == metadata["array_sha256"]
        selection = select_gfs_forecast_as_of(key[1], 120, latency_hours=manifest["latency_hours"])
        assert metadata["cycle_time"] == selection.cycle_time.isoformat()
        assert metadata["availability_time"] == selection.availability_time.isoformat()
        assert metadata["units"] == "mm/h" and metadata["api_crs"] == "EPSG:4326"
        assert metadata["native_cadence_minutes"] == 60 and metadata["output_cadence_minutes"] == 30
        if grid is None:
            grid = metadata["spatial"]["target_grid"]
        assert metadata["spatial"]["target_grid"] == grid
        assert grid["crs"] == "EPSG:32643" and grid["shape"] == [256, 256]
        for window in metadata["windows"]:
            for interval in window["native_intervals"]:
                for source in interval["source_variable_metadata"]:
                    assert source["forecast_reference_time"] == metadata["cycle_time"]
                    assert source["shortName"] == "prate" and source["stepType"] == "avg"
                    assert source["source_uri"].startswith(
                        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
                    )
                    assert len(source["source_message_sha256"]) == 64
        with np.load(folder / "rainfall.npz", allow_pickle=False) as arrays:
            output = arrays["rainfall_rate_mm_h"]
            assert output.shape == (4, 256, 256)
            assert np.isfinite(output).all() and (output >= 0).all()
            assert list(arrays["output_valid_time"]) == expected[key]["target_times"]
            native = [
                HourlyInterval(
                    utc(str(start)),
                    utc(str(end)),
                    rate,
                    [{"forecast_reference_time": metadata["cycle_time"]}],
                    "stored_native_rate",
                    [],
                )
                for start, end, rate in zip(
                    arrays["native_interval_start"],
                    arrays["native_interval_end"],
                    arrays["native_rainfall_rate_mm_h"],
                    strict=True,
                )
            ]
            allocated, _ = allocate_half_hours(native, selection)
            np.testing.assert_allclose(output * 0.5, allocated * 0.5, rtol=2e-6, atol=1e-7)
            low, high = min(low, float(output.min())), max(high, float(output.max()))
            count += output.size
    assert seen == set(expected)
    return {
        "verified_samples": len(seen),
        "verified_output_cells": count,
        "minimum_mm_h": low,
        "maximum_mm_h": high,
        "hashes_grid_schedule_asof_and_temporal_mass_checks": "PASSED",
        "availability_is_assumed_not_observed": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    print(json.dumps(verify(parser.parse_args().root), indent=2))
