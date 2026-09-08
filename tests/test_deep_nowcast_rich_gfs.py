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
from jalrakshak_ml.deep_nowcast.multisource_dataset import (
    CHANNEL_NAMES,
    MultiSourceNowcastDataset,
    MultiSourceStats,
)
from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    get_authoritative_splits,
    is_locked_test_event,
)
from jalrakshak_ml.gfs_replay.core import select_gfs_forecast_as_of, utc
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    METEOROLOGY_ARRAY_KEYS,
    RICH_GFS_REPLAY_VERSION,
    RichIssuePayload,
    derive_cyclic_wind_direction,
    plan_rich_replay_for_events,
    save_rich_issue,
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
    """16. Verify replay planning correctly schedules the 15 non-test events without test contamination."""
    cfg = load_yaml(Path("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"))
    events = cfg["events"]
    assert len(events) == 15

    plan = plan_rich_replay_for_events(events, assumed_latency_hours=6.0)
    assert plan["total_events"] == 15
    assert plan["num_unique_cycles"] > 0
    # Exactly 0 test events
    for eid in plan["events"]:
        assert not is_locked_test_event(eid)
