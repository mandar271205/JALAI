"""Comprehensive Unit and Scientific Integrity Tests for Phase 4E Rich GFS Integration."""
from __future__ import annotations

import json
import math
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import torch

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.multisource_dataset import (
    CHANNEL_NAMES,
    MultiSourceNowcastDataset,
    MultiSourceStats,
    NWP_CHANNELS,
    OBSERVATION_CHANNELS,
    STATIC_CHANNELS,
)
from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    get_authoritative_splits,
    is_locked_test_event,
)
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster
from jalrakshak_ml.gfs_replay.core import select_gfs_forecast_as_of, utc
from jalrakshak_ml.gfs_replay.grib import (
    RICH_VARIABLE_IDX_PATTERNS,
    fetch_rich_gfs_lead,
    rich_index_ranges,
)
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    METEOROLOGY_ARRAY_KEYS,
    RICH_GFS_REPLAY_VERSION,
    RichIssuePayload,
    align_instantaneous_horizons,
    check_colab_drive_persistence,
    derive_cyclic_wind_direction,
    plan_rich_replay_for_events,
    resolve_rich_gfs_output_dir,
    save_rich_issue,
    select_rich_gfs_leads_for_issue,
)
from jalrakshak_ml.gfs_replay.pipeline import build_target_grid
from jalrakshak_ml.gfs_replay.spatial import (
    reproject_field,
    reproject_rate,
)
from jalrakshak_ml.weather.adapters.gfs_rich import (
    GFS_VARIABLE_SPECS,
    derive_wind_speed_and_direction,
)


def test_1_authoritative_split_parsing():
    """1. Verify authoritative 12 train / 3 validation / 3 test split parsing."""
    splits = get_authoritative_splits()
    assert len(splits.train) == 12
    assert len(splits.validation) == 3
    assert len(splits.test) == 3
    assert splits.train == TRAIN_EVENTS_AUTHORITATIVE
    assert splits.validation == VALIDATION_EVENTS_AUTHORITATIVE
    assert splits.test == LOCKED_TEST_EVENTS_AUTHORITATIVE


def test_2_strict_split_disjointness():
    """2. Verify strict disjointness among train, validation, and test sets."""
    splits = get_authoritative_splits()
    train_set = set(splits.train)
    val_set = set(splits.validation)
    test_set = set(splits.test)

    assert train_set.isdisjoint(val_set)
    assert train_set.isdisjoint(test_set)
    assert val_set.isdisjoint(test_set)


def test_3_locked_test_ids_unchanged():
    """3. Verify locked test events are exactly the 3 held-out monsoon events."""
    splits = get_authoritative_splits()
    expected = {
        "mumbai_monsoon_2023_08_24",
        "mumbai_monsoon_2024_08_04",
        "mumbai_monsoon_2024_09_05",
    }
    assert set(splits.test) == expected
    assert is_locked_test_event("mumbai_monsoon_2023_08_24") is True
    assert is_locked_test_event("mumbai_monsoon_2024_08_04") is True
    assert is_locked_test_event("mumbai_monsoon_2024_09_05") is True
    assert is_locked_test_event("mumbai_monsoon_2023_07_18") is False


def test_4_rich_gfs_variable_exact_grib_specs():
    """4. Verify rich GFS variable exact GRIB specifications."""
    required = ("u10", "v10", "t2m", "rh2m", "sp", "cape", "pwat")
    for var in required:
        assert var in GFS_VARIABLE_SPECS
        spec = GFS_VARIABLE_SPECS[var]
        assert "shortName" in spec
        assert "typeOfLevel" in spec
        assert "level" in spec
        assert "stepType" in spec
        assert "canonical_units" in spec
        assert "physical_range" in spec
        min_v, max_v = spec["physical_range"]
        assert min_v < max_v


def test_5_uv_to_wind_speed_correctness():
    """5. Verify u/v horizontal components map to correct wind speed."""
    u = np.array([3.0, 0.0, -6.0], dtype=np.float32)
    v = np.array([4.0, 5.0, 8.0], dtype=np.float32)
    speed, deg, meta = derive_wind_speed_and_direction(u, v)

    expected_speed = np.array([5.0, 5.0, 10.0], dtype=np.float32)
    assert np.allclose(speed, expected_speed, atol=1e-5)
    assert meta["speed_units"] == "m/s"


def test_6_wind_direction_cyclic_encoding_correctness():
    """6. Verify wind direction cyclic sin/cos encoding correctness."""
    # Southerly wind: u=0, v=10 (blowing from South, meteorological direction = 180 deg)
    u = np.array([0.0], dtype=np.float32)
    v = np.array([10.0], dtype=np.float32)
    speed, sin_dir, cos_dir = derive_cyclic_wind_direction(u, v)

    assert np.isclose(speed[0], 10.0, atol=1e-5)
    # At 180 degrees: sin(180) = 0, cos(180) = -1
    assert np.isclose(sin_dir[0], 0.0, atol=1e-4)
    assert np.isclose(cos_dir[0], -1.0, atol=1e-4)

    # Unit circle property: sin^2 + cos^2 = 1.0 for arbitrary random vectors
    rng = np.random.default_rng(42)
    u_rand = rng.normal(0, 5, size=(10, 10)).astype(np.float32)
    v_rand = rng.normal(0, 5, size=(10, 10)).astype(np.float32)
    _, s_rand, c_rand = derive_cyclic_wind_direction(u_rand, v_rand)
    norm = s_rand**2 + c_rand**2
    assert np.allclose(norm, 1.0, atol=1e-5)
    assert np.all(s_rand >= -1.0) and np.all(s_rand <= 1.0)
    assert np.all(c_rand >= -1.0) and np.all(c_rand <= 1.0)


def test_7_rich_replay_storage_schema_and_metadata():
    """7. Verify rich replay storage schema (rainfall.npz, meteorology.npz, metadata.json)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        issue_time = datetime(2023, 7, 18, 6, 0, tzinfo=UTC)
        selection = select_gfs_forecast_as_of(issue_time, 120, latency_hours=6.0)

        # Create mock fields with shape (4, 32, 32)
        rainfall = np.ones((4, 32, 32), dtype=np.float32) * 2.5
        meteo = {
            k: np.ones((4, 32, 32), dtype=np.float32) * 10.0
            for k in METEOROLOGY_ARRAY_KEYS
        }
        spatial = {"target_grid": {"crs": "EPSG:32643", "shape": [32, 32]}}

        payload = RichIssuePayload(
            event_id="mumbai_monsoon_2023_07_18",
            issue_time=issue_time,
            selection=selection,
            rainfall_rate=rainfall,
            meteorology_fields=meteo,
            spatial_metadata=spatial,
        )

        out_path = save_rich_issue(tmpdir, payload)
        assert (out_path / "rainfall.npz").exists()
        assert (out_path / "meteorology.npz").exists()
        assert (out_path / "metadata.json").exists()

        # Check rainfall.npz contents
        with np.load(out_path / "rainfall.npz") as rz:
            assert "rainfall_rate_mm_h" in rz
            assert rz["rainfall_rate_mm_h"].shape == (4, 32, 32)

        # Check meteorology.npz contents
        with np.load(out_path / "meteorology.npz") as mz:
            for k in METEOROLOGY_ARRAY_KEYS:
                assert k in mz
                assert mz[k].shape == (4, 32, 32)

        # Check metadata.json schema
        meta = json.loads((out_path / "metadata.json").read_text(encoding="utf-8"))
        assert meta["native_cadence_minutes"] == 60
        assert meta["output_cadence_minutes"] == 30
        assert "ASSUMED_AVAILABILITY" in meta["qc_flags"]
        assert meta["array_dimensions"] == ["output_horizon", "y", "x"]
        assert "rainfall_sha256" in meta
        assert "meteorology_sha256" in meta


def test_8_missing_channel_semantics():
    """8. Verify missing channel semantics: zero is not automatically missing."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    # Request GPM + GFS precipitation + an ancillary field that does not exist in disk
    ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=("rainfall_gpm", "gfs_precipitation", "gfs_cape"),
        crop_size=(128, 128),
        dropout_prob=0.0,
    )
    sample = ds[0]
    mask = sample["missing_channel_mask"]
    assert mask.shape == (3,)
    # rainfall_gpm is present (False in missing_mask)
    assert mask[0].item() is False
    # gfs_cape has no meteorology.npz on disk in this test path, so marked missing (True in missing_mask)
    assert mask[2].item() is True


def test_9_real_ancillary_channels_not_automatically_zero_masked():
    """9. Verify that when meteorology.npz is available, ancillary channels are loaded and NOT masked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = Path(tmpdir)
        # Populate mock data for first train event sequence (20210618T0130Z or 20230718T0130Z)
        for event_id in ("mumbai_monsoon_2021_06_18", "mumbai_monsoon_2023_07_18"):
            for time_key in ("20210618T0130Z", "20230718T0130Z", "20230718T0600Z"):
                issue_dir = root_dir / event_id / time_key
                issue_dir.mkdir(parents=True, exist_ok=True)
                meteo_data = {
                    k: np.full((4, 256, 256), fill_value=12.5, dtype=np.float32)
                    for k in METEOROLOGY_ARRAY_KEYS
                }
                np.savez(issue_dir / "meteorology.npz", **meteo_data)
                np.savez(
                    issue_dir / "rainfall.npz",
                    rainfall_rate_mm_h=np.full((4, 256, 256), 3.0, dtype=np.float32),
                )

        version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
        ds = MultiSourceNowcastDataset(
            version_dir,
            split="train",
            gfs_replay_root=root_dir,
            active_channels=("rainfall_gpm", "gfs_wind_speed", "gfs_t2m"),
            crop_size=(128, 128),
            dropout_prob=0.0,
        )
        sample = ds[0]
        mask = sample["missing_channel_mask"]

        # Both ancillary channels must be detected and NOT marked missing
        assert mask[1].item() is False
        assert mask[2].item() is False
        # Input tensor must contain the normalized data (not zero)
        assert not torch.all(sample["inputs"][:, 1] == 0.0)
        assert not torch.all(sample["inputs"][:, 2] == 0.0)


def test_10_train_only_normalization():
    """10. Verify normalization parameters fit exclusively on authoritative train events."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    stats = MultiSourceStats.fit_from_training(version_dir)
    assert stats.fitted_split == "train"
    assert stats.fitted_event_ids == TRAIN_EVENTS_AUTHORITATIVE
    assert len(stats.fitted_event_ids) == 12


def test_11_validation_and_test_cannot_affect_normalization():
    """11. Verify validation and test events are strictly forbidden from normalization."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")

    # Attempting to include validation event
    with pytest.raises(ValueError, match="must never contribute to normalization"):
        MultiSourceStats(
            channel_stats={},
            fitted_split="train",
            fitted_event_ids=("mumbai_monsoon_2023_07_25",),  # Validation!
        )

    # Attempting to include locked test event
    with pytest.raises(ValueError, match="must never contribute to normalization"):
        MultiSourceStats(
            channel_stats={},
            fitted_split="train",
            fitted_event_ids=("mumbai_monsoon_2023_08_24",),  # Test!
        )


def test_12_temporal_causality_and_as_of_selection():
    """12. Verify GFS forecast as-of selection strictly obeys causality without lookahead."""
    issue_time = datetime(2023, 7, 18, 9, 30, tzinfo=UTC)
    selection = select_gfs_forecast_as_of(issue_time, 120, latency_hours=6.0)

    # Assumed cycle must be prior to (issue_time - 6h)
    assert selection.cycle_time <= selection.availability_time <= issue_time
    forecast_age = (issue_time - selection.cycle_time).total_seconds() / 3600.0
    assert forecast_age >= 6.0


def test_13_gfs_native_cadence_remains_60_minutes():
    """13. Verify GFS native cadence is documented as 60 minutes in metadata and configs."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    assert cfg["temporal"]["native_cadence_minutes"] == 60
    assert cfg["temporal"]["output_cadence_minutes"] == 30

    channels_cfg = load_yaml(Path("configs/training/multisource_channels_v1.yaml"))
    assert channels_cfg["channels"]["gfs_precipitation"]["native_cadence_minutes"] == 60
    assert channels_cfg["channels"]["gfs_u10"]["native_cadence_minutes"] == 60


def test_14_canonical_output_does_not_claim_new_information():
    """14. Verify spatial reprojection to canonical grid disclaims new meteorological information."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    assert "0.25_deg (~28 km)" in cfg["spatial"]["native_resolution"]


def test_15_immutable_versioned_replay_behavior():
    """15. Verify immutable replay refuses to overwrite conflicting artifacts or test events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        issue_time = datetime(2023, 7, 18, 6, 0, tzinfo=UTC)
        selection = select_gfs_forecast_as_of(issue_time, 120, latency_hours=6.0)

        payload_test = RichIssuePayload(
            event_id="mumbai_monsoon_2023_08_24",  # LOCKED TEST!
            issue_time=issue_time,
            selection=selection,
            rainfall_rate=np.zeros((4, 16, 16), dtype=np.float32),
            meteorology_fields={k: np.zeros((4, 16, 16), dtype=np.float32) for k in METEOROLOGY_ARRAY_KEYS},
            spatial_metadata={"target_grid": {"crs": "EPSG:32643", "shape": [16, 16]}},
        )

        # Attempting to save a locked test event in non-test rich replay must fail loudly
        with pytest.raises(PermissionError, match="LOCKED TEST EVENT"):
            save_rich_issue(tmpdir, payload_test)


def test_16_plan_rich_replay_for_all_15_non_test_events():
    """16. Verify replay planning correctly schedules the 15 non-test events with 17 issues per event."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    events = cfg["events"]
    assert len(events) == 15

    plan = plan_rich_replay_for_events(events, assumed_latency_hours=6.0)
    assert plan["total_events"] == 15
    assert plan["total_issues"] == 255
    assert plan["train_issues"] == 204
    assert plan["validation_issues"] == 51
    assert plan["num_unique_cycles"] == 30

    # Verify locked test events are completely absent
    for eid in plan["events"]:
        assert not is_locked_test_event(eid)

    for eid, ev_data in plan["events"].items():
        assert ev_data["num_issues"] == 17, f"Event {eid} must have 17 issues, got {ev_data['num_issues']}"
        assert len(ev_data["issues"]) == 17

        # First issue time must be 01:30, last issue time must be 09:30
        first_issue = ev_data["issues"][0]
        last_issue = ev_data["issues"][-1]
        assert first_issue["issue_time"].endswith("01:30:00+00:00") or first_issue["issue_time"].endswith("01:30:00Z")
        assert last_issue["issue_time"].endswith("09:30:00+00:00") or last_issue["issue_time"].endswith("09:30:00Z")

        for issue in ev_data["issues"]:
            # Every issue must have all 4 future target timestamps available in the GPM event
            assert len(issue["target_times"]) == 4
            issue_dt = datetime.fromisoformat(issue["issue_time"].replace("Z", "+00:00"))
            for h_idx, target_str in enumerate(issue["target_times"]):
                target_dt = datetime.fromisoformat(target_str.replace("Z", "+00:00"))
                expected_delta = (h_idx + 1) * 30
                assert (target_dt - issue_dt).total_seconds() / 60.0 == expected_delta
                # Must be strictly within the 12-hour event window (0 to 11.5 hours)
                event_start_dt = issue_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                assert (target_dt - event_start_dt).total_seconds() / 60.0 <= 690  # 11:30 UTC is max frame


def test_17_planner_timestamps_exact_equality_with_dataset_indices():
    """17. Verify planner issue timestamps match MultiSourceNowcastDataset sequence indices exactly."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    events = cfg["events"]
    plan = plan_rich_replay_for_events(events, assumed_latency_hours=6.0)

    # For train events in dataset
    ds_train = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=("rainfall_gpm",),
    )
    for eid in set(item.event_id for item in ds_train.indices):
        dataset_issue_times = [
            item.input_times[-1]
            for item in ds_train.indices
            if item.event_id == eid
        ]
        assert len(dataset_issue_times) == 17
        planner_issue_times = [
            issue["issue_time"]
            for issue in plan["events"][eid]["issues"]
        ]
        assert planner_issue_times == dataset_issue_times, (
            f"Mismatch between dataset indices and planner for {eid}!\n"
            f"Dataset: {dataset_issue_times}\nPlanner: {planner_issue_times}"
        )

    # For validation events in dataset
    ds_val = MultiSourceNowcastDataset(
        version_dir,
        split="validation",
        active_channels=("rainfall_gpm",),
    )
    for eid in set(item.event_id for item in ds_val.indices):
        dataset_issue_times = [
            item.input_times[-1]
            for item in ds_val.indices
            if item.event_id == eid
        ]
        assert len(dataset_issue_times) == 17
        planner_issue_times = [
            issue["issue_time"]
            for issue in plan["events"][eid]["issues"]
        ]
        assert planner_issue_times == dataset_issue_times, (
            f"Mismatch between validation dataset indices and planner for {eid}!\n"
            f"Dataset: {dataset_issue_times}\nPlanner: {planner_issue_times}"
        )


# =========================================================================
# PHASE 4E PRE-DOWNLOAD AUDIT FIX VERIFICATION SUITE (TESTS 1 - 18)
# =========================================================================

SAMPLE_NOAA_IDX_TEXT = """1:0:d=2023071800:PRATE:surface:0-1 hour ave fcst:
2:100000:d=2023071800:UGRD:10 m above ground:1 hour fcst:
3:220000:d=2023071800:VGRD:10 m above ground:1 hour fcst:
4:340000:d=2023071800:TMP:2 m above ground:1 hour fcst:
5:460000:d=2023071800:RH:2 m above ground:1 hour fcst:
6:580000:d=2023071800:PRES:surface:1 hour fcst:
7:700000:d=2023071800:CAPE:surface:1 hour fcst:
8:820000:d=2023071800:PWAT:entire atmosphere (considered as a single layer):1 hour fcst:
9:950000:d=2023071800:HGT:500 mb:1 hour fcst:
"""


def test_fix1_negative_uv_wind_reprojection():
    """1. negative u/v wind reprojection: signed values preserved without finite_rain rejection."""
    lat = np.arange(18.0, 20.26, 0.25)
    lon = np.arange(72.0, 74.01, 0.25)
    source_values = np.full((len(lat), len(lon)), -8.5, dtype=np.float32)
    source_values[0, 0] = 5.0
    source_values[-1, -1] = -12.0

    target_grid = build_target_grid(
        bbox_wgs84=[72.7, 18.8, 73.1, 19.3],
        analysis_crs="EPSG:32643",
        width=32,
        height=32,
    )

    out_arr, meta = reproject_field(
        source_values,
        lat,
        lon,
        target_grid,
        variable_name="u10",
        physical_range=(-100.0, 100.0),
    )
    assert out_arr.shape == (32, 32)
    assert np.isfinite(out_arr).all()
    # Negative values must be preserved
    assert (out_arr < 0.0).any()
    assert meta["interpolation_method"] == "bilinear"
    assert meta["physical_range"] == [-100.0, 100.0]

    # Out of range values must fail
    with pytest.raises(ValueError, match="physical_range"):
        reproject_field(
            source_values,
            lat,
            lon,
            target_grid,
            variable_name="u10",
            physical_range=(-5.0, 5.0),
        )

    # reproject_rate on negative values must reject (precipitation-specific non-negativity)
    with pytest.raises(ValueError, match="non-negative"):
        reproject_rate(source_values, lat, lon, target_grid)


def test_fix2_rich_idx_message_selection():
    """2. rich .idx message selection: exact parameter matching for all 7 rich variables + precipitation."""
    ranges = rich_index_ranges(SAMPLE_NOAA_IDX_TEXT, lead_hour=1)
    for v in ("prate", "u10", "v10", "t2m", "rh2m", "sp", "cape", "pwat"):
        assert v in ranges
        start, end = ranges[v]
        assert start < end


def test_fix3_ambiguous_or_missing_grib_field_rejection():
    """3. ambiguous/missing GRIB field rejection: fail loudly on bad .idx definitions."""
    # Missing required variable
    idx_missing = """1:0:d=2023071800:PRATE:surface:0-1 hour ave fcst:
2:100000:d=2023071800:VGRD:10 m above ground:1 hour fcst:
"""
    with pytest.raises(ValueError, match="Missing required GRIB messages in .idx"):
        rich_index_ranges(idx_missing, lead_hour=1)

    # Duplicate / ambiguous variable definition
    idx_ambiguous = """1:0:d=2023071800:UGRD:10 m above ground:1 hour fcst:
2:100000:d=2023071800:UGRD:10 m above ground:1 hour fcst:
3:200000:d=2023071800:VGRD:10 m above ground:1 hour fcst:
"""
    with pytest.raises(ValueError, match="Ambiguous"):
        rich_index_ranges(idx_ambiguous, lead_hour=1)


def test_fix4_byte_range_computation():
    """4. byte-range computation: precise byte boundary offsets calculated from adjacent .idx lines."""
    ranges = rich_index_ranges(SAMPLE_NOAA_IDX_TEXT, lead_hour=1)
    assert ranges["prate"] == (0, 100000 - 1)
    assert ranges["u10"] == (100000, 220000 - 1)
    assert ranges["v10"] == (220000, 340000 - 1)
    assert ranges["t2m"] == (340000, 460000 - 1)
    assert ranges["rh2m"] == (460000, 580000 - 1)
    assert ranges["sp"] == (580000, 700000 - 1)
    assert ranges["cape"] == (700000, 820000 - 1)
    assert ranges["pwat"] == (820000, 950000 - 1)


def test_fix5_no_full_grib_fallback():
    """5. no full-GRIB fallback: dry-run and download plans confirm full_grib_download_required=False."""
    res = fetch_rich_gfs_lead(
        cycle_dt=datetime(2023, 7, 18, 0, 0, tzinfo=UTC),
        lead_hour=1,
        dry_run=True,
    )
    assert res["status"] == "dry_run"
    assert res["full_grib_download_required"] is False
    assert len(res["ranges"]) == 8


def test_fix6_minimal_lead_selection_225_total_pairs():
    """6. minimal lead selection = 225 total unique cycle+lead pairs across 15 non-test events."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    events = cfg["events"]
    plan = plan_rich_replay_for_events(events, assumed_latency_hours=6.0)

    assert plan["unique_cycles_count"] == 30
    assert plan["unique_cycle_lead_pairs_count"] == 225
    assert plan["total_issues"] == 255
    assert plan["overfetch_fixed"] is True


def test_fix7_causal_cycle_availability():
    """7. causal cycle availability: selected cycle time satisfies assumed_availability <= issue_time."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    events = cfg["events"]
    plan = plan_rich_replay_for_events(events, assumed_latency_hours=6.0)

    for eid, edata in plan["events"].items():
        for issue in edata["issues"]:
            issue_dt = datetime.fromisoformat(issue["issue_time"])
            cycle_dt = datetime.fromisoformat(issue["cycle_time"])
            assert cycle_dt + timedelta(hours=6) <= issue_dt
            assert issue["cycle_availability_status"] == "ASSUMED"


def test_fix8_instantaneous_temporal_alignment():
    """8. instantaneous temporal alignment: latest native valid time <= target valid time."""
    issue_dt = datetime(2023, 7, 18, 1, 30, tzinfo=UTC)
    cycle_dt = datetime(2023, 7, 17, 18, 0, tzinfo=UTC)
    alignments = align_instantaneous_horizons(cycle_dt, issue_dt)

    assert len(alignments) == 4
    for al in alignments:
        assert al.source_valid_time <= al.target_valid_time
        assert 0 <= al.age_minutes < 60

    # Horizon +30m (02:00 UTC) -> source 02:00 (lead 8, age 0m)
    assert alignments[0].horizon_minutes == 30
    assert alignments[0].selected_lead_hour == 8
    assert alignments[0].age_minutes == 0

    # Horizon +60m (02:30 UTC) -> source 02:00 (lead 8, age 30m)
    assert alignments[1].horizon_minutes == 60
    assert alignments[1].selected_lead_hour == 8
    assert alignments[1].age_minutes == 30

    # Horizon +90m (03:00 UTC) -> source 03:00 (lead 9, age 0m)
    assert alignments[2].horizon_minutes == 90
    assert alignments[2].selected_lead_hour == 9
    assert alignments[2].age_minutes == 0

    # Horizon +120m (03:30 UTC) -> source 03:00 (lead 9, age 30m)
    assert alignments[3].horizon_minutes == 120
    assert alignments[3].selected_lead_hour == 9
    assert alignments[3].age_minutes == 30


def test_fix9_to_14_decoupled_temporal_dataset_architecture():
    """9-14. Verification of obs_history, nwp_future, target, and static feature separation."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=CHANNEL_NAMES,
        crop_size=(128, 128),
        dropout_prob=0.0,
    )
    sample = ds[0]

    # 9. obs_history timestamps
    obs_times = sample["obs_times"]
    assert len(obs_times) == 4
    for i in range(1, 4):
        t_prev = datetime.fromisoformat(obs_times[i-1])
        t_curr = datetime.fromisoformat(obs_times[i])
        assert (t_curr - t_prev).total_seconds() == 1800
    assert obs_times[-1] == sample["issue_time"]

    # 10. nwp_future timestamps
    nwp_times = sample["nwp_valid_times"]
    assert len(nwp_times) == 4
    issue_dt = datetime.fromisoformat(sample["issue_time"])
    assert datetime.fromisoformat(nwp_times[0]) == issue_dt + timedelta(minutes=30)
    assert datetime.fromisoformat(nwp_times[3]) == issue_dt + timedelta(minutes=120)

    # 11. target timestamps
    target_times = sample["target_times"]
    assert len(target_times) == 4
    assert datetime.fromisoformat(target_times[0]) == issue_dt + timedelta(minutes=30)
    assert datetime.fromisoformat(target_times[3]) == issue_dt + timedelta(minutes=120)

    # 12. nwp/target horizon alignment
    assert nwp_times == target_times

    # 13. static feature shape [C_static=1, H, W] without fake temporal axis
    assert sample["static_features"].shape == (1, 128, 128)
    assert sample["static_features"].ndim == 3

    # 14. no temporal-axis collision
    assert sample["obs_history"].shape == (4, 1, 128, 128)
    assert sample["nwp_future"].shape == (4, 11, 128, 128)
    assert sample["target"].shape == (4, 1, 128, 128)
    assert sample["target_physical"].shape == (4, 1, 128, 128)


def test_fix15_missing_channel_masks():
    """15. missing-channel masks: fine-grained masks for obs, nwp, static, and active channels."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=CHANNEL_NAMES,
        dropout_prob=1.0,
        rng_seed=42,
    )
    sample = ds[0]
    # Observation rainfall is never dropped
    assert sample["missing_obs_mask"][0].item() is False
    # All optional NWP channels dropped under prob 1.0
    assert sample["missing_nwp_mask"].all().item() is True
    assert sample["missing_channel_mask"][0].item() is False


def test_fix16_locked_test_exclusion():
    """16. locked test exclusion: locked test events can never be loaded in train/val or normalization."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    for locked_id in LOCKED_TEST_EVENTS_AUTHORITATIVE:
        assert is_locked_test_event(locked_id) is True
        with pytest.raises(ValueError, match="CRITICAL"):
            MultiSourceStats.fit_from_training(version_dir, train_event_ids=(locked_id,))


def test_fix17_drive_output_override_and_dry_run(monkeypatch):
    """17. Drive output override/dry-run: CLI and env overrides work, and Colab ephemeral path warns."""
    custom_dir = Path("tmp/custom_rich_gfs")
    monkeypatch.setenv("JALAI_RICH_GFS_DIR", str(custom_dir))
    assert resolve_rich_gfs_output_dir(None) == custom_dir

    cli_dir = Path("tmp/cli_rich_gfs")
    assert resolve_rich_gfs_output_dir(cli_dir) == cli_dir

    with pytest.warns(UserWarning, match="EPHEMERAL STORAGE WARNING"):
        check_colab_drive_persistence(Path("/content/JALAI/data/processed/gfs_replay"))


def test_fix18_legacy_baseline_and_model_compatibility():
    """18. legacy baseline compatibility: ConvLSTM V3, U-Net, and ST-Attention work with both legacy and separated inputs."""
    m1 = ConvLSTMNowcasterV3(input_channels=3)
    m2 = UNetConvGRUNowcaster(input_channels=3)
    m3 = STAttentionNowcasterV1(input_channels=3)

    # Legacy calling convention
    x = torch.randn(2, 4, 3, 128, 128)
    p = torch.clamp(torch.randn(2, 1, 128, 128), min=0.0)

    out1 = m1(x, p)
    out2 = m2(x, p)
    out3 = m3(x, p)
    assert out1.shape == (2, 4, 1, 128, 128)
    assert out2.shape == (2, 4, 1, 128, 128)
    assert out3.shape == (2, 4, 1, 128, 128)
    assert (out1 >= 0.0).all()
    assert (out2 >= 0.0).all()
    assert (out3 >= 0.0).all()

    # Separated conditioning calling convention
    m1_sep = ConvLSTMNowcasterV3(input_channels=13)
    obs = torch.randn(2, 4, 1, 128, 128)
    nwp = torch.randn(2, 4, 11, 128, 128)
    static = torch.randn(2, 1, 128, 128)

    out_sep = m1_sep(obs_history=obs, nwp_future=nwp, static_features=static, persistence_baseline=p)
    assert out_sep.shape == (2, 4, 1, 128, 128)
    assert (out_sep >= 0.0).all()

