"""Physical, spatial, provenance, and no-future-vintage checks for Phase 4A."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import xy

from jalrakshak_ml.config import load_pilot_config, load_yaml
from jalrakshak_ml.gfs_replay.core import (
    LOCKED_EVENTS,
    allocate_half_hours,
    interval_amount,
    reconstruct_hourly,
    select_gfs_forecast_as_of,
    utc,
)
from jalrakshak_ml.gfs_replay.grib import choose_exact, index_range, read_field, selector
from jalrakshak_ml.gfs_replay.pipeline import save_issue
from jalrakshak_ml.gfs_replay.schedule import materialize_schedule, validate_events
from jalrakshak_ml.gfs_replay.spatial import canonicalize_grid, reproject_rate
from jalrakshak_ml.preprocessing.grid import build_target_grid

ROOT = Path(__file__).resolve().parents[1]
CYCLE = utc("2023-08-24T00:00:00+00:00")


def meta(start=0, end=1, product="prate", cycle=CYCLE):
    return {
        "shortName": product,
        "typeOfLevel": "surface",
        "level": 0,
        "stepType": "avg" if product == "prate" else "accum",
        "startStep": start,
        "endStep": end,
        "stepUnits": "h",
        "units": "kg m**-2 s**-1" if product == "prate" else "kg m**-2",
        "forecast_reference_time": cycle.isoformat(),
        "valid_time": (cycle + timedelta(hours=end)).isoformat(),
        "source_uri": f"https://example.test/f{end:03d}",
    }


def fields(n=9, rate=2.0):
    return [(np.full((2, 2), rate / 3600), meta(((h - 1) // 6) * 6, h)) for h in range(1, n + 1)]


def test_exact_field_selection_ignores_wrong_first_variable():
    good = meta()
    wrong = {**good, "shortName": "sp"}
    assert choose_exact([wrong, good], selector("prate_mean", CYCLE, 1)) is good


@pytest.mark.parametrize("messages", [[], [meta(), meta()], [{**meta(), "level": 2}]])
def test_missing_ambiguous_or_wrong_level_rejected(messages):
    with pytest.raises(ValueError, match="missing or ambiguous"):
        choose_exact(messages, selector("prate_mean", CYCLE, 1))


def test_parser_uses_exact_metadata_and_real_coordinates(monkeypatch, tmp_path):
    import jalrakshak_ml.gfs_replay.grib as module

    base = {
        **meta(),
        "dataDate": 20230824,
        "dataTime": 0,
        "validityDate": 20230824,
        "validityTime": 100,
        "stepUnits": 1,
        "gridType": "regular_ll",
        "paramId": 3059,
        "productDefinitionTemplateNumber": 8,
        "missingValue": 9999,
    }
    records = [{**base, "shortName": "vis"}, base]
    lat = np.arange(18, 20.26, 0.25)
    lon = np.arange(72, 74.01, 0.25)

    class FakeCodes:
        def __init__(self):
            self.i = 0
            self.released = []

        def codes_grib_new_from_file(self, stream):
            if self.i == len(records):
                return None
            self.i += 1
            return self.i

        def codes_get(self, gid, key):
            return records[gid - 1][key]

        def codes_get_array(self, gid, key):
            return np.repeat(lat, len(lon)) if key == "latitudes" else np.tile(lon, len(lat))

        def codes_get_values(self, gid):
            assert gid == 2  # Wrong first variable must not even be decoded.
            return np.full(len(lat) * len(lon), 2 / 3600)

        def codes_release(self, gid):
            self.released.append(gid)

    fake = FakeCodes()
    monkeypatch.setattr(module, "eccodes_module", lambda: fake)
    path = tmp_path / "mock.grib2"
    path.touch()
    arr, lats, lons, record = read_field(
        path, selector("prate_mean", CYCLE, 1), [72.75, 18.85, 73.05, 19.3]
    )
    assert np.allclose(arr, 2 / 3600)
    assert np.all(np.diff(lats) < 0) and np.all(np.diff(lons) > 0)
    assert record["units"] == "kg m**-2 s**-1"
    assert fake.released == [1, 2]


def test_apcp_amount_to_interval_rate_and_prate_conversion():
    amount = interval_amount(np.array([6.0]), meta(0, 3, "tp"))
    assert amount.item() / 3 == 2.0
    amount = interval_amount(np.array([2 / 3600]), meta(0, 3))
    assert amount.item() / 3 == pytest.approx(2.0)


@pytest.mark.parametrize(
    "bad",
    [
        meta(0, 0),
        {**meta(), "stepType": "instant"},
        {**meta(), "units": "K"},
        {**meta(), "shortName": "vis"},
    ],
)
def test_invalid_precipitation_metadata_rejected(bad):
    with pytest.raises(ValueError):
        interval_amount(np.array([1.0]), bad)


@pytest.mark.parametrize("bad", [-1.0, np.nan, np.inf])
def test_nonfinite_or_negative_rain_rejected(bad):
    with pytest.raises(ValueError):
        interval_amount(np.array([bad]), meta())


def test_cumulative_differencing_and_explicit_reset():
    source = [
        (np.array([h * 2.0 if h <= 6 else 2.0]), meta(0 if h <= 6 else 6, h, "tp"))
        for h in range(1, 8)
    ]
    result = reconstruct_hourly(source)
    assert len(result) == 7
    assert all(np.allclose(item.rate, 2) for item in result)
    assert result[-1].qc_flags == ["EXPLICIT_ACCUMULATION_ORIGIN_RESET"]
    assert len(result[1].sources) == 2


@pytest.mark.parametrize(
    "source",
    [
        [(np.array([5.0]), meta(0, 1, "tp")), (np.array([3.0]), meta(0, 2, "tp"))],
        [
            (np.array([5.0]), meta(0, 1, "tp")),
            (np.array([6.0]), meta(0, 2, "tp", CYCLE + timedelta(hours=6))),
        ],
        [(np.array([5.0]), meta(0, 1, "tp")), (np.array([6.0]), meta(0, 3, "tp"))],
        [(np.array([5.0]), meta(0, 1, "tp")), (np.array([6.0]), meta(0, 1, "tp"))],
        [(np.array([5.0]), meta(0, 2, "tp"))],
    ],
)
def test_resets_mixed_cycles_gaps_and_duplicate_leads_fail(source):
    with pytest.raises(ValueError):
        reconstruct_hourly(source)


def test_nonconstant_hourly_mean_reconstruction():
    source = [(np.array([2 / 3600]), meta(0, 1)), (np.array([4 / 3600]), meta(0, 2))]
    result = reconstruct_hourly(source)
    assert result[0].rate.item() == pytest.approx(2)
    assert result[1].rate.item() == pytest.approx(6)


def test_hourly_half_hour_mass_conservation():
    selection = select_gfs_forecast_as_of(CYCLE + timedelta(hours=6), 120)
    native = reconstruct_hourly(fields())
    output, windows = allocate_half_hours(native, selection)
    assert output.shape == (4, 2, 2)
    np.testing.assert_allclose(output, 2)
    np.testing.assert_allclose(output.sum(axis=0) * 0.5, 4)
    assert windows[0]["native_intervals"][0]["overlap_minutes"] == 30
    assert [w["horizon_minutes"] for w in windows] == [30, 60, 90, 120]


def test_missing_output_interval_rejected():
    selection = select_gfs_forecast_as_of(CYCLE + timedelta(hours=6), 120)
    with pytest.raises(ValueError, match="Missing output interval"):
        allocate_half_hours(reconstruct_hourly(fields(7)), selection)


def test_asof_selector_rejects_future_and_unavailable_cycles():
    issue = CYCLE + timedelta(hours=7, minutes=30)
    selection = select_gfs_forecast_as_of(issue, 120)
    assert selection.cycle_time == CYCLE
    assert selection.availability_time == CYCLE + timedelta(hours=6)
    assert selection.forecast_hours[-1] == 10
    with pytest.raises(ValueError, match="No known available"):
        select_gfs_forecast_as_of(
            issue,
            120,
            known_availability={
                (CYCLE + timedelta(hours=6)).isoformat(): (CYCLE + timedelta(hours=8)).isoformat()
            },
        )
    known = select_gfs_forecast_as_of(
        issue,
        120,
        known_availability={
            CYCLE.isoformat(): (CYCLE + timedelta(hours=3)).isoformat(),
            (CYCLE + timedelta(hours=12)).isoformat(): (CYCLE + timedelta(hours=15)).isoformat(),
        },
    )
    assert known.cycle_time == CYCLE
    with pytest.raises(ValueError, match="temporal leakage"):
        replace(selection, availability_time=issue + timedelta(minutes=1)).validate()


def test_halfhour_issue_uses_same_vintage_and_future_valid_times():
    selection = select_gfs_forecast_as_of(CYCLE + timedelta(hours=6, minutes=30), 120)
    output, windows = allocate_half_hours(reconstruct_hourly(fields()), selection)
    assert np.isfinite(output).all() and (output >= 0).all()
    assert windows[-1]["output_valid_time"] == (CYCLE + timedelta(hours=8, minutes=30)).isoformat()
    wrong = fields()
    wrong = [
        (
            v,
            {
                **m,
                "forecast_reference_time": (CYCLE + timedelta(hours=6)).isoformat(),
                "valid_time": (CYCLE + timedelta(hours=6 + m["endStep"])).isoformat(),
            },
        )
        for v, m in wrong
    ]
    with pytest.raises(ValueError, match="cycle leakage"):
        allocate_half_hours(reconstruct_hourly(wrong), selection)


def test_source_affine_center_and_orientation():
    arr = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    sorted_arr, _, _, affine = canonicalize_grid(arr, [18.75, 19, 19.25], [433, 432.75, 432.5])
    assert sorted_arr[0, 0] == 9
    assert xy(affine, 0, 0) == (72.5, 19.25)
    assert affine.e == -0.25 and affine.a == 0.25


def target():
    pilot = load_pilot_config(ROOT / "configs/pilot/mumbai.yaml")
    return build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"], analysis_crs=pilot["analysis_crs"], width=256, height=256
    )


def test_target_grid_alignment_and_no_added_resolution():
    lat = np.arange(18, 20.26, 0.25)
    lon = np.arange(72, 74.01, 0.25)
    result, provenance = reproject_rate(np.full((len(lat), len(lon)), 2.0), lat, lon, target())
    np.testing.assert_allclose(result, 2)
    assert result.shape == (256, 256)
    assert provenance["target_grid"]["affine"] == list(target()["transform"])[:6]
    assert provenance["source_resolution_degrees"] == [0.25, 0.25]
    with pytest.raises(ValueError, match="coverage|halo"):
        reproject_rate(np.ones((2, 2)), [19.25, 19], [72.75, 73], target())


def test_index_transport_disambiguates_prate_not_instant():
    text = "1:0:d=2023082400:PRATE:surface:1 hour fcst:\n2:100:d=2023082400:PRATE:surface:0-1 hour ave fcst:\n3:300:d=2023082400:APCP:surface:0-1 hour acc fcst:"
    assert index_range(text, "prate_mean", 1) == (100, 299)
    with pytest.raises(ValueError):
        index_range(text, "prate_mean", 2)


def test_versioned_schedule_uses_existing_indexer_for_51_samples(tmp_path):
    cfg = load_yaml(ROOT / "configs/replay/gfs_mumbai_v1.yaml")
    manifest, path = materialize_schedule(cfg, tmp_path)
    assert path.exists() and manifest["total_samples"] == 51
    assert manifest["sequence_indexer"] == "RainfallSequenceDataset._index_event"
    for event in manifest["events"]:
        assert len(event["samples"]) == 17
        first, last = event["samples"][0], event["samples"][-1]
        assert first["issue_time"][11:16] == "01:30"
        assert last["issue_time"][11:16] == "09:30"
        assert last["target_times"][-1][11:16] == "11:30"
    invalid = [{**event, "split": "train"} for event in cfg["events"]]
    with pytest.raises(ValueError):
        validate_events(invalid)


def test_storage_has_provenance_nonnegative_arrays_and_no_overwrite(tmp_path):
    selection = select_gfs_forecast_as_of(CYCLE + timedelta(hours=6), 120)
    native = reconstruct_hourly(fields(8))
    lat = np.arange(18, 20.26, 0.25)
    lon = np.arange(72, 74.01, 0.25)
    rate, spatial = reproject_rate(np.full((len(lat), len(lon)), 2.0), lat, lon, target())
    native = [replace(interval, rate=rate) for interval in native]
    destination, metadata = save_issue(
        tmp_path, LOCKED_EVENTS[0], selection, native, spatial, "benchmark-test"
    )
    assert (
        json.loads((destination / "metadata.json").read_text())["cycle_time"] == CYCLE.isoformat()
    )
    assert metadata["units"] == "mm/h" and metadata["api_crs"] == "EPSG:4326"
    assert metadata["forecast_age_hours"] == 6
    source = metadata["windows"][0]["native_intervals"][0]["source_variable_metadata"][0]
    assert "source_uri" in source and "startStep" in source and "units" in source
    with np.load(destination / "rainfall.npz") as saved:
        assert saved["rainfall_rate_mm_h"].shape == (4, 256, 256)
        assert np.isfinite(saved["rainfall_rate_mm_h"]).all()
    with pytest.raises(FileExistsError):
        save_issue(tmp_path, LOCKED_EVENTS[0], selection, native, spatial, "benchmark-test")
    reused, reused_metadata = save_issue(
        tmp_path,
        LOCKED_EVENTS[0],
        selection,
        native,
        spatial,
        "benchmark-test",
        reuse_verified=True,
    )
    assert reused == destination and reused_metadata == metadata
    with pytest.raises(ValueError, match="provenance/hash"):
        save_issue(
            tmp_path,
            LOCKED_EVENTS[0],
            selection,
            native,
            spatial,
            "different-benchmark",
            reuse_verified=True,
        )
