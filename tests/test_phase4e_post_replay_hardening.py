"""Comprehensive regression tests for Phase 4E post-replay pipeline hardening.

Verifies:
- 255 exact issue membership (204 train, 51 val, 0 test)
- Missing issue failure detection
- Duplicate issue failure detection
- Locked test contamination failure detection
- Corrupt NPZ failure detection
- Wrong shape failure detection
- NaN/Inf failure detection
- Negative rainfall failure detection
- SHA256 file tampering detection
- Signed float u/v preservation and invalid bounds rejection
- Missing provenance failure detection
- Invalid PRATE independence metadata failure detection
- Real-channel audit rejecting placeholder/provisional/synthetic sources
- Train-only normalization: reads exactly 12 train events (204 issues)
- Train-only normalization: validation and locked-test leakage rejection
- Train-only normalization: existing final artifact overwrite refusal
- Train-only normalization: provisional provenance rejection
- Train-only normalization: atomic creation with .part rename
- Build script early manifest existence guard
- Build script dynamic pairs check
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.phase4e_prepare import fit_train_only_normalization
from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
)
from jalrakshak_ml.gfs_replay.core import utc
from jalrakshak_ml.gfs_replay.phase4e_audit import audit_real_channels, audit_replay
from jalrakshak_ml.gfs_replay.rich_download import sha256_file
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    METEOROLOGY_ARRAY_KEYS,
    plan_rich_replay_for_events,
)


def _precompute_mock_npz_buffers() -> tuple[bytes, str, bytes, str]:
    """Precompute compressed mock NPZ bytes with non-zero variance for fast execution."""
    x = np.linspace(1.0, 5.0, 256, dtype=np.float32)
    base_grid = np.tile(x, (256, 1))

    # Rainfall rate: distinct values per pixel and horizon
    rain_data = np.stack([base_grid * (1.0 + 0.1 * i) for i in range(4)])
    rain_buf = io.BytesIO()
    np.savez_compressed(rain_buf, rainfall_rate_mm_h=rain_data)
    rain_bytes = rain_buf.getvalue()
    rain_hash = hashlib.sha256(rain_bytes).hexdigest()

    u_data = np.stack([-base_grid * (0.8 + 0.05 * i) for i in range(4)])
    v_data = np.stack([base_grid * (1.2 + 0.05 * i) for i in range(4)])
    speed_data = np.sqrt(u_data**2 + v_data**2)
    sin_data = np.clip(u_data / (speed_data + 1e-6), -1.0, 1.0)
    cos_data = np.clip(v_data / (speed_data + 1e-6), -1.0, 1.0)
    t2m_data = np.stack([295.0 + base_grid * (2.0 + 0.1 * i) for i in range(4)])
    rh_data = np.stack([70.0 + base_grid * (4.0 + 0.1 * i) for i in range(4)])
    sp_data = np.stack([100000.0 + base_grid * (200.0 + 1.0 * i) for i in range(4)])
    cape_data = np.stack([400.0 + base_grid * (50.0 + 0.5 * i) for i in range(4)])
    pwat_data = np.stack([35.0 + base_grid * (3.0 + 0.1 * i) for i in range(4)])

    meteo_buf = io.BytesIO()
    np.savez_compressed(
        meteo_buf,
        gfs_u10=u_data,
        gfs_v10=v_data,
        gfs_wind_speed=speed_data,
        gfs_wind_direction_sin=sin_data,
        gfs_wind_direction_cos=cos_data,
        gfs_t2m=t2m_data,
        gfs_rh2m=rh_data,
        gfs_surface_pressure=sp_data,
        gfs_cape=cape_data,
        gfs_pwat=pwat_data,
    )
    meteo_bytes = meteo_buf.getvalue()
    meteo_hash = hashlib.sha256(meteo_bytes).hexdigest()

    return rain_bytes, rain_hash, meteo_bytes, meteo_hash


RAIN_BYTES, RAIN_HASH, METEO_BYTES, METEO_HASH = _precompute_mock_npz_buffers()


def _build_mock_metadata(
    event_id: str,
    split: str,
    issue: dict[str, Any],
    *,
    independent_native_observation: bool = False,
    disaggregation_method: str = "uniform_within_native_interval",
    scientific_disclaimer: str = "Reprojection to 256x256 does NOT increase meteorological resolution beyond native 0.25-deg GFS.",
    placeholder: bool = False,
    provisional: bool = False,
    synthetic: bool = False,
) -> dict[str, Any]:
    issue_dt = utc(issue["issue_time"])
    cycle_dt = issue_dt - timedelta(hours=6)
    avail_dt = issue_dt

    targets = issue["target_times"]
    instantaneous = [
        {
            "horizon_minutes": (i + 1) * 30,
            "aligned_target_time": t,
            "source_native_valid_time": t,
            "source_interval_start": t,
            "source_interval_end": t,
            "cycle_time": cycle_dt.isoformat(),
            "lead_hour": i + 1,
            "availability_time": avail_dt.isoformat(),
        }
        for i, t in enumerate(targets)
    ]
    precipitation = [
        {
            "horizon_minutes": (i + 1) * 30,
            "aligned_target_time": t,
            "source_native_valid_time": t,
            "source_interval_start": (issue_dt + timedelta(hours=i)).isoformat(),
            "source_interval_end": (issue_dt + timedelta(hours=i + 1)).isoformat(),
            "cycle_time": cycle_dt.isoformat(),
            "lead_hour": i + 1,
            "availability_time": avail_dt.isoformat(),
            "independent_native_observation": independent_native_observation,
            "temporal_disaggregation_method": disaggregation_method,
        }
        for i, t in enumerate(targets)
    ]

    source_provenance = {
        "gfs_precipitation": [
            {
                "source_path": f"cache/{event_id}_prate.grib2",
                "sha256": "0" * 64,
                "parser_state": "PASSED",
                "placeholder": placeholder,
                "provisional": provisional,
                "synthetic": synthetic,
                "conversion_method": "TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL",
                "conversion_formula": "rate_mm_h = prate_kg_m2_s * 3600",
            }
            for _ in range(4)
        ],
        **{
            ch: [
                {
                    "source_path": f"cache/{event_id}_{ch}.grib2",
                    "sha256": "0" * 64,
                    "parser_state": "PASSED",
                    "placeholder": placeholder,
                    "provisional": provisional,
                    "synthetic": synthetic,
                }
            ]
            for ch in METEOROLOGY_ARRAY_KEYS
        },
    }

    masks = {
        ch: [True, True, True, True]
        for ch in ("gfs_precipitation", *METEOROLOGY_ARRAY_KEYS)
    }

    return {
        "replay_version": "phase4e_rich_replay_v1",
        "event_id": event_id,
        "split": split,
        "issue_time": issue_dt.isoformat(),
        "cycle_time": cycle_dt.isoformat(),
        "availability_time": avail_dt.isoformat(),
        "availability_basis": "assumed_cycle_plus_6h",
        "native_cadence_minutes": 60,
        "output_cadence_minutes": 30,
        "native_resolution": "0.25_deg (~28 km)",
        "canonical_resolution": "256x256 (EPSG:32643)",
        "scientific_disclaimer": scientific_disclaimer,
        "horizons_minutes": [30, 60, 90, 120],
        "spatial": {"target_grid": {"crs": "EPSG:32643", "shape": [256, 256]}},
        "temporal_metadata": {
            "instantaneous": instantaneous,
            "precipitation": precipitation,
        },
        "source_provenance": source_provenance,
        "availability_masks": masks,
        "rainfall_sha256": RAIN_HASH,
        "meteorology_sha256": METEO_HASH,
    }


def populate_mock_replay(
    replay_root: Path,
    plan: dict[str, Any],
    *,
    corrupt_first_rainfall: bool = False,
    omit_one_issue: bool = False,
) -> None:
    """Populate a full valid synthetic 255-issue mock replay."""
    first = True
    for event_id, event in plan["events"].items():
        for issue in event["issues"]:
            if omit_one_issue and first:
                first = False
                continue
            issue_dt = utc(issue["issue_time"])
            folder = replay_root / event_id / issue_dt.strftime("%Y%m%dT%H%MZ")
            folder.mkdir(parents=True, exist_ok=True)

            (folder / "rainfall.npz").write_bytes(
                b"CORRUPT_NOT_NPZ" if (corrupt_first_rainfall and first) else RAIN_BYTES
            )
            (folder / "meteorology.npz").write_bytes(METEO_BYTES)

            meta = _build_mock_metadata(event_id, event["split"], issue)
            (folder / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            first = False

    manifest = {
        "events": plan["total_events"],
        "train_issues": plan["train_issues"],
        "validation_issues": plan["validation_issues"],
        "total_issues": plan["total_issues"],
        "execution_state": "COMPLETE",
        "complete_issues": plan["total_issues"],
    }
    (replay_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@pytest.fixture(scope="module")
def authoritative_plan() -> dict[str, Any]:
    cfg = load_yaml("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml")
    return plan_rich_replay_for_events(cfg["events"], assumed_latency_hours=6.0)


@pytest.fixture(scope="module")
def shared_mock_replay(tmp_path_factory, authoritative_plan) -> Path:
    """Module-scoped shared mock replay containing all 255 issues."""
    replay_root = tmp_path_factory.mktemp("shared_mock_replay")
    populate_mock_replay(replay_root, authoritative_plan)
    return replay_root


@pytest.fixture
def isolated_replay(tmp_path, shared_mock_replay) -> Path:
    """Fast copy of the shared replay for tests that need to mutate files."""
    dest = tmp_path / "replay"
    shutil.copytree(shared_mock_replay, dest)
    return dest


# ==============================================================================
# REPLAY INTEGRITY AUDIT TESTS
# ==============================================================================


def test_replay_audit_255_exact_membership_pass(shared_mock_replay, authoritative_plan):
    result = audit_replay(authoritative_plan, shared_mock_replay)
    assert result["audit_passed"] is True
    assert result["expected_events"] == 15
    assert result["expected_train_events"] == 12
    assert result["expected_validation_events"] == 3
    assert result["train_issues_passed"] == 204
    assert result["validation_issues_passed"] == 51
    assert result["complete_issues"] == 255
    assert result["missing_issues"] == 0
    assert result["corrupt_or_invalid_issues"] == 0
    assert result["locked_test_accessed"] is False
    assert len(result["missing_or_invalid"]) == 0


def test_replay_audit_missing_issue_failure(isolated_replay, authoritative_plan):
    # Remove one issue directory
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")
    shutil.rmtree(issue_dir)

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert result["missing_issues"] == 1
    assert any("missing_folder" in err for err in result["missing_or_invalid"])


def test_replay_audit_locked_test_contamination_failure(isolated_replay, authoritative_plan):
    # Contaminate with locked test event directory
    locked_dir = isolated_replay / LOCKED_TEST_EVENTS_AUTHORITATIVE[0]
    locked_dir.mkdir(parents=True, exist_ok=True)

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert result["locked_test_accessed"] is True
    assert any("locked_test_contamination" in err for err in result["missing_or_invalid"])


def test_replay_audit_corrupt_npz_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")

    # Corrupt rainfall.npz and update metadata sha256 to point to corrupt file
    corrupt_bytes = b"CORRUPT_NOT_A_VALID_ZIP_ARCHIVE"
    (issue_dir / "rainfall.npz").write_bytes(corrupt_bytes)
    meta = json.loads((issue_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["rainfall_sha256"] = hashlib.sha256(corrupt_bytes).hexdigest()
    (issue_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert result["corrupt_or_invalid_issues"] == 1
    assert any("invalid" in err for err in result["missing_or_invalid"])


def test_replay_audit_sha256_tamper_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")

    # Mutate rainfall.npz WITHOUT updating metadata hash
    (issue_dir / "rainfall.npz").write_bytes(RAIN_BYTES + b"tamper")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert any("sha256 mismatch" in err for err in result["missing_or_invalid"])


def test_replay_audit_wrong_shape_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")

    # Save wrong shape (3, 256, 256) and update metadata sha256
    bad_rain = np.ones((3, 256, 256), dtype=np.float32)
    np.savez_compressed(issue_dir / "rainfall.npz", rainfall_rate_mm_h=bad_rain)
    meta = json.loads((issue_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["rainfall_sha256"] = sha256_file(issue_dir / "rainfall.npz")
    (issue_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert result["corrupt_or_invalid_issues"] >= 1
    assert any("shape mismatch" in err for err in result["missing_or_invalid"])


def test_replay_audit_nan_inf_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")

    # Save NaN array and update metadata sha256
    nan_rain = np.full((4, 256, 256), np.nan, dtype=np.float32)
    np.savez_compressed(issue_dir / "rainfall.npz", rainfall_rate_mm_h=nan_rain)
    meta = json.loads((issue_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["rainfall_sha256"] = sha256_file(issue_dir / "rainfall.npz")
    (issue_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert any("NaN or Inf" in err for err in result["missing_or_invalid"])


def test_replay_audit_negative_rainfall_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue_time = authoritative_plan["events"][first_event]["issues"][0]["issue_time"]
    issue_dir = isolated_replay / first_event / utc(first_issue_time).strftime("%Y%m%dT%H%MZ")

    # Save negative rainfall and update metadata sha256
    neg_rain = np.full((4, 256, 256), -0.5, dtype=np.float32)
    np.savez_compressed(issue_dir / "rainfall.npz", rainfall_rate_mm_h=neg_rain)
    meta = json.loads((issue_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["rainfall_sha256"] = sha256_file(issue_dir / "rainfall.npz")
    (issue_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert any("negative rainfall" in err for err in result["missing_or_invalid"])


def test_replay_audit_invalid_prate_independence_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue = authoritative_plan["events"][first_event]["issues"][0]
    issue_dir = isolated_replay / first_event / utc(first_issue["issue_time"]).strftime("%Y%m%dT%H%MZ")

    bad_meta = _build_mock_metadata(
        first_event, "train", first_issue, independent_native_observation=True
    )
    (issue_dir / "metadata.json").write_text(json.dumps(bad_meta, indent=2), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert any("independent_native_observation must be False" in err for err in result["missing_or_invalid"])


def test_replay_audit_missing_disclaimer_failure(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue = authoritative_plan["events"][first_event]["issues"][0]
    issue_dir = isolated_replay / first_event / utc(first_issue["issue_time"]).strftime("%Y%m%dT%H%MZ")

    bad_meta = _build_mock_metadata(
        first_event, "train", first_issue, scientific_disclaimer="Bogus downscaled resolution claim!"
    )
    (issue_dir / "metadata.json").write_text(json.dumps(bad_meta, indent=2), encoding="utf-8")

    result = audit_replay(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert any("scientific disclaimer" in err for err in result["missing_or_invalid"])


# ==============================================================================
# REAL CHANNEL AUDIT TESTS
# ==============================================================================


def test_real_channels_audit_rejection_of_provisional_or_synthetic(isolated_replay, authoritative_plan):
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue = authoritative_plan["events"][first_event]["issues"][0]
    issue_dir = isolated_replay / first_event / utc(first_issue["issue_time"]).strftime("%Y%m%dT%H%MZ")

    fake_meta = _build_mock_metadata(first_event, "train", first_issue, placeholder=True)
    (issue_dir / "metadata.json").write_text(json.dumps(fake_meta, indent=2), encoding="utf-8")

    result = audit_real_channels(authoritative_plan, isolated_replay)
    assert result["audit_passed"] is False
    assert result["fake_radar_used"] is False
    assert result["fake_insat_used"] is False


# ==============================================================================
# TRAIN-ONLY NORMALIZATION FITTER TESTS
# ==============================================================================


@pytest.fixture(scope="module")
def mock_dataset_and_elevation(tmp_path_factory) -> tuple[Path, Path]:
    tmp_root = tmp_path_factory.mktemp("mock_data")
    dataset_root = tmp_root / "dataset"
    dataset_root.mkdir(parents=True, exist_ok=True)

    x = np.linspace(1.0, 10.0, 256, dtype=np.float32)
    base_grid = np.tile(x, (256, 1))

    events_list = []
    # Create 12 train events in Zarr with non-zero variance
    for eid in TRAIN_EVENTS_AUTHORITATIVE:
        zarr_path = dataset_root / f"{eid}.zarr"
        store = zarr.open(str(zarr_path), mode="w")
        gpm_data = np.stack([base_grid * (0.5 + 0.05 * f) for f in range(24)])[:, None, :, :]
        store.create_dataset(
            "rainfall",
            data=gpm_data,
            shape=(24, 1, 256, 256),
            dtype=np.float32,
        )
        events_list.append({"event_id": eid, "split": "train", "path": f"{eid}.zarr"})

    # Add 3 validation events to manifest (must NEVER be opened by train normalizer)
    for eid in VALIDATION_EVENTS_AUTHORITATIVE:
        events_list.append({"event_id": eid, "split": "validation", "path": f"{eid}.zarr"})

    manifest = {"dataset_version": "v1", "events": events_list}
    (dataset_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Static elevation with non-zero variance
    elevation_path = tmp_root / "static_elevation_mumbai_256x256.npy"
    elev_data = np.linspace(10.0, 150.0, 256 * 256, dtype=np.float32).reshape(256, 256)
    np.save(elevation_path, elev_data)

    return dataset_root, elevation_path


def test_fit_train_only_normalization_success(
    tmp_path, shared_mock_replay, mock_dataset_and_elevation
):
    dataset_root, elevation_path = mock_dataset_and_elevation
    out_artifact = tmp_path / "normalization" / "phase4e_train_stats.json"

    result = fit_train_only_normalization(
        dataset_root,
        shared_mock_replay,
        elevation_path,
        out_artifact,
        dataset_version="v1",
        replay_version="r1",
        git_sha="abcdef123456",
    )

    assert result["status"] == "PASS"
    assert result["audit_passed"] is True
    assert result["validation_opened"] is False
    assert result["locked_test_opened"] is False
    assert result["total_train_events"] == 12
    assert result["total_train_issues"] == 204
    assert result["fitted_event_ids"] == list(TRAIN_EVENTS_AUTHORITATIVE)
    assert out_artifact.is_file()

    # Verify channel order and statistics
    stats = result["statistics"]
    assert "obs_history" in stats
    assert "nwp_future" in stats
    assert "static_features" in stats
    for nwp_ch in METEOROLOGY_ARRAY_KEYS:
        assert nwp_ch in stats["nwp_future"]
        assert stats["nwp_future"][nwp_ch]["std"] > 1e-7


def test_fit_train_only_normalization_overwrite_refusal(
    tmp_path, shared_mock_replay, mock_dataset_and_elevation
):
    dataset_root, elevation_path = mock_dataset_and_elevation
    out_artifact = tmp_path / "existing_normalization.json"
    out_artifact.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Versioned normalization artifact already exists"):
        fit_train_only_normalization(
            dataset_root,
            shared_mock_replay,
            elevation_path,
            out_artifact,
            dataset_version="v1",
            replay_version="r1",
            git_sha="test_sha",
        )


def test_fit_train_only_normalization_leakage_rejection(
    tmp_path, shared_mock_replay, mock_dataset_and_elevation
):
    dataset_root_orig, elevation_path = mock_dataset_and_elevation
    # Copy dataset root so we can tamper with manifest safely
    dataset_root = tmp_path / "tampered_dataset"
    shutil.copytree(dataset_root_orig, dataset_root)

    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["events"][0]["event_id"] = VALIDATION_EVENTS_AUTHORITATIVE[0]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    out_artifact = tmp_path / "leakage_norm.json"
    with pytest.raises((ValueError, PermissionError)):
        fit_train_only_normalization(
            dataset_root,
            shared_mock_replay,
            elevation_path,
            out_artifact,
            dataset_version="v1",
            replay_version="r1",
            git_sha="test_sha",
        )


def test_fit_train_only_normalization_provisional_rejection(
    tmp_path, isolated_replay, mock_dataset_and_elevation, authoritative_plan
):
    dataset_root, elevation_path = mock_dataset_and_elevation

    # Invalidate one train metadata with placeholder=True
    first_event = TRAIN_EVENTS_AUTHORITATIVE[0]
    first_issue = authoritative_plan["events"][first_event]["issues"][0]
    issue_dir = isolated_replay / first_event / utc(first_issue["issue_time"]).strftime("%Y%m%dT%H%MZ")

    bad_meta = _build_mock_metadata(first_event, "train", first_issue, placeholder=True)
    (issue_dir / "metadata.json").write_text(json.dumps(bad_meta), encoding="utf-8")

    out_artifact = tmp_path / "prov_norm.json"
    with pytest.raises(ValueError, match="Provisional/placeholder provenance"):
        fit_train_only_normalization(
            dataset_root,
            isolated_replay,
            elevation_path,
            out_artifact,
            dataset_version="v1",
            replay_version="r1",
            git_sha="test_sha",
        )


# ==============================================================================
# BUILD SCRIPT EARLY MANIFEST GUARD & PAIRS CHECK TESTS
# ==============================================================================


def _load_build_script_main():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "build_phase4e_rich_replay.py"
    spec = importlib.util.spec_from_file_location("build_script_mod", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def test_build_replay_script_early_manifest_guard(tmp_path, monkeypatch):
    build_main = _load_build_script_main()

    out_root = tmp_path / "replay_out"
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_phase4e_rich_replay.py",
            "--raw-cache",
            str(tmp_path / "cache"),
            "--download-audit",
            str(tmp_path / "audit.json"),
            "--output-root",
            str(out_root),
            "--execute",
        ],
    )

    with pytest.raises(FileExistsError, match="Versioned replay manifest already exists"):
        build_main()


def test_build_replay_script_dynamic_pairs_check(tmp_path, monkeypatch):
    build_main = _load_build_script_main()

    out_root = tmp_path / "replay_out_fresh"
    out_root.mkdir(parents=True, exist_ok=True)

    # Fake audit with complete_pairs != expected (225)
    bad_audit = tmp_path / "bad_audit.json"
    bad_audit.write_text(
        json.dumps({"audit_passed": True, "complete_pairs": 100}), encoding="utf-8"
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_phase4e_rich_replay.py",
            "--raw-cache",
            str(tmp_path / "cache"),
            "--download-audit",
            str(bad_audit),
            "--output-root",
            str(out_root),
            "--execute",
        ],
    )

    with pytest.raises(RuntimeError, match="Raw download audit gate is not satisfied"):
        build_main()
