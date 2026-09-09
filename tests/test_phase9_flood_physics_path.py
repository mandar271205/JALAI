"""Test suite: Workstream D + F + H — flood-physics execution path and FNO readiness.

Covers:
- MumbaiDomainRecord construction and serialization
- DEM NaN repair (nearest-neighbor, no interpolation)
- Rainfall .bdy file generation from GPM cubes and existing forcing
- LISFLOOD-FP par/bci file rendering
- Solver execution wrapper: BLOCKED_NO_BINARY and BLOCKED_MISSING_INPUT paths
- FNO readiness: architecture, nonnegative output, loss, metrics, checkpoint structure
- Claim gate integrity: LISFLOOD_SMOKE_EXECUTED=False honoured, fabrication blocked

Phase 4E training data is never touched.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch


# ────────────────────────────────────────────────────────────────────────────
# Domain preparation
# ────────────────────────────────────────────────────────────────────────────

class TestMumbaiDomain:
    def test_domain_record_construction(self):
        from jalrakshak_ml.flood.domain import MumbaiDomainRecord
        rec = MumbaiDomainRecord(
            domain_id="test_v1",
            created_at="2026-01-01T00:00:00+00:00",
            crs="EPSG:32643",
            grid_shape=(256, 256),
            transform=(125.68, 0.0, 262927.81, 0.0, -196.08, 2135557.25),
            nodata=float("nan"),
            pixel_resolution_m=196.08,
            bbox_wgs84=(72.75, 18.85, 73.05, 19.30),
            dem_path="data/processed/static/elevation.tif",
            dem_source="copernicus_glo_30",
            dem_nan_cells=1685,
            dem_finite_cells=256 * 256 - 1685,
            dem_min_m=-0.60,
            dem_max_m=479.30,
            dem_repaired=False,
            dem_repair_method=None,
            roughness_path="data/processed/static/roughness.tif",
            roughness_source="esa_worldcover_manning_lookup",
            roughness_calibrated=False,
            roughness_min=0.015,
            roughness_max=0.04,
            slope_path="data/processed/static/slope.tif",
            domain_mask_path=None,
            boundary_conditions={"type": "open_coastal", "calibrated": False},
            forcing_schema={"source": "GPM_IMERG_V07", "cadence_minutes": 30},
            slope_available=True,
            flow_accumulation_available=True,
            low_lying_index_available=True,
            provenance={"synthetic": False, "dem_source": "copernicus_glo_30"},
            assumed_parameters=("roughness:uncalibrated_literature",),
            blockers=(),
        )
        assert rec.domain_id == "test_v1"
        assert rec.crs == "EPSG:32643"
        assert rec.roughness_calibrated is False
        assert rec.dem_repaired is False
        assert "type" in rec.boundary_conditions

    def test_domain_record_content_hash_is_deterministic(self):
        from jalrakshak_ml.flood.domain import MumbaiDomainRecord
        kwargs = dict(
            domain_id="test_v1", created_at="2026-01-01T00:00:00+00:00",
            crs="EPSG:32643", grid_shape=(256, 256),
            transform=(125.68, 0.0, 262927.81, 0.0, -196.08, 2135557.25),
            nodata=float("nan"), pixel_resolution_m=196.08,
            bbox_wgs84=(72.75, 18.85, 73.05, 19.30),
            dem_path="a.tif", dem_source="copernicus_glo_30",
            dem_nan_cells=0, dem_finite_cells=100,
            dem_min_m=0.0, dem_max_m=10.0,
            dem_repaired=False, dem_repair_method=None,
            roughness_path="r.tif", roughness_source="esa",
            roughness_calibrated=False, roughness_min=0.015, roughness_max=0.04,
            slope_path=None, domain_mask_path=None,
            boundary_conditions={"type": "open"}, forcing_schema={"source": "gpm"},
            slope_available=False, flow_accumulation_available=False,
            low_lying_index_available=False,
            provenance={"synthetic": False},
            assumed_parameters=(),
            blockers=(),
        )
        r1 = MumbaiDomainRecord(**kwargs)
        r2 = MumbaiDomainRecord(**kwargs)
        assert r1.content_hash() == r2.content_hash()

    def test_domain_record_write_is_atomic(self, tmp_path):
        from jalrakshak_ml.flood.domain import MumbaiDomainRecord
        rec = MumbaiDomainRecord(
            domain_id="write_test", created_at="2026-01-01T00:00:00+00:00",
            crs="EPSG:32643", grid_shape=(4, 4),
            transform=(1.0, 0.0, 0.0, 0.0, -1.0, 0.0),
            nodata=float("nan"), pixel_resolution_m=1.0,
            bbox_wgs84=(0.0, 0.0, 1.0, 1.0),
            dem_path="a.tif", dem_source="copernicus_glo_30",
            dem_nan_cells=0, dem_finite_cells=16,
            dem_min_m=0.0, dem_max_m=5.0,
            dem_repaired=False, dem_repair_method=None,
            roughness_path="r.tif", roughness_source="esa",
            roughness_calibrated=False, roughness_min=0.015, roughness_max=0.04,
            slope_path=None, domain_mask_path=None,
            boundary_conditions={"type": "open"}, forcing_schema={"source": "gpm"},
            slope_available=False, flow_accumulation_available=False,
            low_lying_index_available=False,
            provenance={"synthetic": False},
            assumed_parameters=(), blockers=(),
        )
        out = tmp_path / "domain.json"
        rec.write(out)
        assert out.is_file()
        data = json.loads(out.read_text())
        assert data["domain_id"] == "write_test"
        assert "content_sha256" in data
        assert not (tmp_path / "domain.json.part").exists()

    def test_prepare_mumbai_domain_with_real_files(self, tmp_path):
        """Functional test against real data files."""
        dem_path = Path("data/processed/static/elevation.tif")
        roughness_path = Path("data/processed/static/roughness.tif")
        if not dem_path.is_file() or not roughness_path.is_file():
            pytest.skip("Real DEM/roughness not present")

        from jalrakshak_ml.flood.domain import prepare_mumbai_domain
        record = prepare_mumbai_domain(
            dem_path=dem_path,
            roughness_path=roughness_path,
            output_path=tmp_path / "domain.json",
            repair_nan_cells=True,
        )
        assert record.grid_shape == (256, 256)
        assert record.crs == "EPSG:32643"
        assert record.roughness_calibrated is False
        assert record.dem_nan_cells >= 0
        assert record.dem_finite_cells > 0
        if record.dem_nan_cells > 0:
            # If scipy is available, repair should succeed
            try:
                import scipy  # noqa: F401
                assert record.dem_repaired is True
                assert record.dem_repair_method is not None
            except ImportError:
                pass  # scipy optional
        assert "LISFLOOD" in str(record.boundary_conditions).upper() or record.boundary_conditions


# ────────────────────────────────────────────────────────────────────────────
# GPM → forcing adapter
# ────────────────────────────────────────────────────────────────────────────

class TestGPMForcing:
    def test_write_bdy_from_synthetic_rates(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import write_lisflood_bdy
        rates = np.array([5.0, 12.3, 20.0, 10.0, 3.5], dtype=np.float64)
        bdy_path, meta = write_lisflood_bdy(
            rates, event_id="test_event", start_time_iso="2021-06-18T00:00:00+00:00",
            output_path=tmp_path / "test.bdy",
        )
        assert bdy_path.is_file()
        assert meta["units"] == "mm/h"
        assert meta["n_timesteps"] == 5
        assert meta["cadence_minutes"] == 30
        assert meta["sub_grid_spatial_detail"] == "NOT_MODELLED"
        assert meta["source"] == "gpm_imerg_v07"
        # Verify .json sidecar
        meta_file = bdy_path.with_suffix(".json")
        assert meta_file.is_file()

    def test_bdy_rates_are_preserved(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import write_lisflood_bdy
        rates = np.array([1.0, 2.5, 100.0], dtype=np.float64)
        bdy_path, _ = write_lisflood_bdy(
            rates, event_id="e1", start_time_iso="2021-01-01T00:00:00+00:00",
            output_path=tmp_path / "e1.bdy",
        )
        content = bdy_path.read_text()
        assert "1.0000" in content
        assert "2.5000" in content
        assert "100.0000" in content

    def test_bdy_rejects_negative_rates(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import write_lisflood_bdy
        with pytest.raises(ValueError, match="non-negative"):
            write_lisflood_bdy(
                np.array([-1.0, 5.0]),
                event_id="neg", start_time_iso="2021-01-01T00:00:00+00:00",
                output_path=tmp_path / "neg.bdy",
            )

    def test_bdy_rejects_nan_rates(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import write_lisflood_bdy
        with pytest.raises(ValueError, match="finite"):
            write_lisflood_bdy(
                np.array([float("nan"), 5.0]),
                event_id="nan_test", start_time_iso="2021-01-01T00:00:00+00:00",
                output_path=tmp_path / "nan.bdy",
            )

    def test_cube_to_domain_average_rates(self):
        from jalrakshak_ml.flood.gpm_to_forcing import cube_to_domain_average_rates
        rng = np.random.default_rng(42)
        cube = rng.uniform(0, 50, (10, 8, 8)).astype(np.float32)
        rates = cube_to_domain_average_rates(cube)
        assert rates.shape == (10,)
        assert np.isfinite(rates).all()
        np.testing.assert_allclose(rates[0], cube[0].mean(), rtol=1e-4)

    def test_load_gpm_cube_2d_promoted_to_3d(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import load_gpm_cube
        arr = np.ones((4, 4), dtype=np.float32) * 10.0
        cube_path = tmp_path / "single_frame.npy"
        np.save(cube_path, arr)
        cube = load_gpm_cube(cube_path)
        assert cube.ndim == 3
        assert cube.shape == (1, 4, 4)

    def test_load_gpm_cube_clips_negative(self, tmp_path):
        from jalrakshak_ml.flood.gpm_to_forcing import load_gpm_cube
        arr = np.array([[[5.0, -1.0], [0.0, 2.0]]], dtype=np.float32)
        p = tmp_path / "neg.npy"
        np.save(p, arr)
        cube = load_gpm_cube(p)
        assert (cube >= 0).all()

    def test_existing_bdy_parsing_returns_metadata(self):
        from jalrakshak_ml.flood.gpm_to_forcing import build_forcing_from_existing_bdy
        bdy_path = Path("data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.bdy")
        if not bdy_path.is_file():
            pytest.skip("Forcing file not present")
        meta = build_forcing_from_existing_bdy(bdy_path)
        assert "n_timesteps" in meta or "forcing_file" in meta

    def test_existing_bdy_missing_raises(self):
        from jalrakshak_ml.flood.gpm_to_forcing import build_forcing_from_existing_bdy
        with pytest.raises(FileNotFoundError):
            build_forcing_from_existing_bdy("/nonexistent/forcing.bdy")


# ────────────────────────────────────────────────────────────────────────────
# LISFLOOD-FP parameter file
# ────────────────────────────────────────────────────────────────────────────

class TestLISFLOODParFile:
    def _spec(self, tmp_path) -> "LISFLOODParFile":
        from jalrakshak_ml.flood.lisflood_adapter import LISFLOODParFile
        return LISFLOODParFile(
            scenario_id="test_smoke",
            dem_path=str(tmp_path / "dem.tif"),
            roughness_path=str(tmp_path / "roughness.tif"),
            bdy_path=str(tmp_path / "rain.bdy"),
            output_dir=str(tmp_path / "out"),
            dx_m=160.88,
            dy_m=196.08,
            nrows=256,
            ncols=256,
            sim_time_hours=1.0,
        )

    def test_par_renders_required_fields(self, tmp_path):
        spec = self._spec(tmp_path)
        text = spec.render_par_text()
        assert "DEMfile" in text
        assert "manningfile" in text
        assert "bdyfile" in text
        assert "dx" in text
        assert "solver" in text
        assert "rainfall" in text
        assert "Calibrated: False" in text

    def test_par_write_creates_files(self, tmp_path):
        spec = self._spec(tmp_path)
        par_path, bci_path = spec.write(tmp_path / "work")
        assert par_path.is_file()
        assert bci_path.is_file()

    def test_write_lisflood_par_utility(self, tmp_path):
        from jalrakshak_ml.flood.lisflood_adapter import write_lisflood_par
        spec, par_path, bci_path = write_lisflood_par(
            "smoke_v1",
            dem_path=tmp_path / "dem.tif",
            roughness_path=tmp_path / "r.tif",
            bdy_path=tmp_path / "rain.bdy",
            output_dir=tmp_path / "out",
            sim_time_hours=0.5,
        )
        assert par_path.is_file()
        assert spec.sim_time_hours == 0.5

    def test_assumed_parameters_documented_in_par(self, tmp_path):
        spec = self._spec(tmp_path)
        text = spec.render_par_text()
        assert "uncalibrated" in text.lower() or "assumed" in text.lower()


# ────────────────────────────────────────────────────────────────────────────
# LISFLOOD-FP smoke execution
# ────────────────────────────────────────────────────────────────────────────

class TestLISFLOODExecution:
    def test_blocked_when_binary_absent(self, tmp_path):
        from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
        # Create minimal input files
        dem = tmp_path / "dem.tif"
        roughness = tmp_path / "r.tif"
        bdy = tmp_path / "rain.bdy"
        dem.write_bytes(b"fake_dem")
        roughness.write_bytes(b"fake_roughness")
        bdy.write_text("rainfall_test\n1 hours\n0.00\t10.0\n")

        record = run_lisflood_smoke(
            dem_path=dem,
            roughness_path=roughness,
            bdy_path=bdy,
            output_dir=tmp_path / "out",
            executable="definitely_not_installed_lisflood_xyz",
        )
        assert record.execution_status == "BLOCKED_NO_BINARY"
        assert record.physically_simulated is False
        assert record.max_depth_m is None

    def test_blocked_when_dem_missing(self, tmp_path):
        from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
        record = run_lisflood_smoke(
            dem_path=tmp_path / "nonexistent.tif",
            roughness_path=tmp_path / "r.tif",
            bdy_path=tmp_path / "rain.bdy",
            output_dir=tmp_path / "out",
        )
        assert record.execution_status == "BLOCKED_MISSING_INPUT"
        assert record.physically_simulated is False

    def test_run_record_is_serializable(self, tmp_path):
        from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
        dem = tmp_path / "dem.tif"
        roughness = tmp_path / "r.tif"
        bdy = tmp_path / "rain.bdy"
        dem.write_bytes(b"fake_dem")
        roughness.write_bytes(b"fake_roughness")
        bdy.write_text("rainfall_test\n1 hours\n0.00\t10.0\n")

        record = run_lisflood_smoke(
            dem_path=dem, roughness_path=roughness, bdy_path=bdy,
            output_dir=tmp_path / "out",
            executable="definitely_not_installed_lisflood_xyz",
        )
        data = record.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["execution_status"] == "BLOCKED_NO_BINARY"
        assert parsed["physically_simulated"] is False

    def test_run_record_write_is_atomic(self, tmp_path):
        from jalrakshak_ml.flood.lisflood_adapter import LISFLOODRunRecord
        record = LISFLOODRunRecord(
            scenario_id="test", execution_status="BLOCKED_NO_BINARY",
            solver_binary=None, solver_version=None, exit_code=None,
            runtime_seconds=None, stdout_tail="", stderr_tail="no binary",
            par_file_sha256="N/A", dem_sha256="N/A",
            roughness_sha256="N/A", forcing_sha256="N/A",
            output_files=[], max_depth_m=None, inundated_cells=None,
            physically_simulated=False,
        )
        out = tmp_path / "record.json"
        record.write(out)
        assert out.is_file()
        assert not out.with_suffix(".json.part").exists()
        data = json.loads(out.read_text())
        assert data["physically_simulated"] is False

    def test_failed_execution_returns_correct_status(self, tmp_path, monkeypatch):
        from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke, find_lisflood_binary
        dem = tmp_path / "dem.tif"
        roughness = tmp_path / "r.tif"
        bdy = tmp_path / "rain.bdy"
        dem.write_bytes(b"fake")
        roughness.write_bytes(b"fake")
        bdy.write_text("rainfall_test\n1 hours\n0.00\t10.0\n")

        def mock_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="solver crashed")

        monkeypatch.setattr("jalrakshak_ml.flood.lisflood_adapter.subprocess.run", mock_run)
        monkeypatch.setattr("jalrakshak_ml.flood.lisflood_adapter.find_lisflood_binary", lambda: "/fake/lisflood")

        record = run_lisflood_smoke(
            dem_path=dem, roughness_path=roughness, bdy_path=bdy,
            output_dir=tmp_path / "out",
        )
        assert record.execution_status == "FAILED"
        assert record.physically_simulated is False
        assert record.exit_code == 1


# ────────────────────────────────────────────────────────────────────────────
# FNO readiness audit
# ────────────────────────────────────────────────────────────────────────────

class TestFNOReadiness:
    def test_fno_readiness_all_checks_pass(self):
        from jalrakshak_ml.flood.fno_readiness import audit_fno_readiness
        report = audit_fno_readiness(width=8, modes=4, output_horizons=4, grid_size=16)
        assert report.architecture_correct
        assert report.output_nonnegative
        assert report.loss_forward_pass
        assert report.metrics_callable
        assert report.checkpoint_structure_valid
        assert not report.blockers
        assert report.ready_for_training

    def test_fno_readiness_6_channel_contract(self):
        from jalrakshak_ml.flood.fno_readiness import audit_fno_readiness
        report = audit_fno_readiness()
        assert len(report.recommended_input_channels) == 6
        assert "dem_m" in report.recommended_input_channels
        assert "rainfall_mm_h" in report.recommended_input_channels
        assert "roughness_n" in report.recommended_input_channels

    def test_fno_training_blocked_by_absence_of_genuine_targets(self):
        from jalrakshak_ml.flood.fno_readiness import audit_fno_readiness
        report = audit_fno_readiness()
        config = report.smoke_train_config
        assert "GENUINE_SOLVER_OUTPUT_AVAILABLE=False" in config.get("blocker_for_training", "")

    def test_fno_readiness_report_serializable(self):
        from jalrakshak_ml.flood.fno_readiness import audit_fno_readiness
        report = audit_fno_readiness(width=4, modes=2, output_horizons=2, grid_size=8)
        data = report.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["ready_for_training"] is True

    def test_fno_readiness_write_report(self, tmp_path):
        from jalrakshak_ml.flood.fno_readiness import write_fno_readiness_report
        report = write_fno_readiness_report(
            output_path=tmp_path / "fno_readiness.json",
            width=4, modes=2, grid_size=8
        )
        assert (tmp_path / "fno_readiness.json").is_file()
        data = json.loads((tmp_path / "fno_readiness.json").read_text())
        assert "ready_for_training" in data


# ────────────────────────────────────────────────────────────────────────────
# Claim gate integrity
# ────────────────────────────────────────────────────────────────────────────

class TestClaimGates:
    def test_authoritative_gates_valid(self):
        from jalrakshak_ml.core.claim_gates import AUTHORITATIVE_GATES
        g = AUTHORITATIVE_GATES
        assert g.PHYSICS_DOMAIN_READY is True
        assert g.RAINFALL_FORCING_READY is True
        assert g.LISFLOOD_EXECUTABLE is False
        assert g.LISFLOOD_SMOKE_EXECUTED is False
        assert g.GENUINE_SOLVER_OUTPUT_AVAILABLE is False
        assert g.FNO_READY_FOR_SMOKE is True
        assert g.FNO_ACTUALLY_TRAINED is False
        assert g.FABRICATED_DEPTH_USED is False

    def test_smoke_executed_without_binary_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="solver binary"):
            ScientificClaimGates(
                LISFLOOD_SMOKE_EXECUTED=True,
                LISFLOOD_EXECUTABLE=False,
            )

    def test_genuine_output_without_smoke_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="executed smoke run"):
            ScientificClaimGates(
                GENUINE_SOLVER_OUTPUT_AVAILABLE=True,
                LISFLOOD_SMOKE_EXECUTED=False,
                LISFLOOD_EXECUTABLE=False,
            )

    def test_dataset_ready_without_output_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="genuine solver output"):
            ScientificClaimGates(
                PHYSICS_DATASET_READY=True,
                GENUINE_SOLVER_OUTPUT_AVAILABLE=False,
                LISFLOOD_SMOKE_EXECUTED=False,
                LISFLOOD_EXECUTABLE=False,
            )

    def test_fno_trained_without_dataset_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="frozen genuine physics dataset"):
            ScientificClaimGates(
                FNO_ACTUALLY_TRAINED=True,
                PHYSICS_DATASET_READY=False,
                GENUINE_SOLVER_OUTPUT_AVAILABLE=False,
                LISFLOOD_SMOKE_EXECUTED=False,
                LISFLOOD_EXECUTABLE=False,
            )

    def test_roughness_calibrated_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="uncalibrated"):
            ScientificClaimGates(ROUGHNESS_CALIBRATED=True)

    def test_fabricated_depth_raises(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError, match="Fabrication"):
            ScientificClaimGates(FABRICATED_DEPTH_USED=True)

    def test_susceptibility_not_depth_invariant(self):
        from jalrakshak_ml.core.claim_gates import ScientificClaimGates
        with pytest.raises(ValueError):
            ScientificClaimGates(SUSCEPTIBILITY_IS_NOT_DEPTH=False)


# ────────────────────────────────────────────────────────────────────────────
# Integration: existing .bdy + par file + readiness
# ────────────────────────────────────────────────────────────────────────────

class TestEndToEndPreparation:
    def test_existing_forcing_and_par_file_pipeline(self, tmp_path):
        """Integration test: use existing forcing file, write par, run FNO audit."""
        bdy_path = Path("data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.bdy")
        if not bdy_path.is_file():
            pytest.skip("Existing forcing file not present")

        from jalrakshak_ml.flood.gpm_to_forcing import build_forcing_from_existing_bdy
        from jalrakshak_ml.flood.lisflood_adapter import write_lisflood_par
        from jalrakshak_ml.flood.fno_readiness import audit_fno_readiness

        meta = build_forcing_from_existing_bdy(bdy_path)
        assert meta is not None

        spec, par_path, bci_path = write_lisflood_par(
            "integration_test",
            dem_path="data/processed/static/elevation.tif",
            roughness_path="data/processed/static/roughness.tif",
            bdy_path=str(bdy_path),
            output_dir=str(tmp_path / "out"),
            sim_time_hours=0.5,
            work_dir=tmp_path / "par",
        )
        assert par_path.is_file()
        content = par_path.read_text()
        assert "mumbai_smoke" in content.lower() or "integration_test" in content.lower()

        fno = audit_fno_readiness(width=4, modes=2, grid_size=8)
        assert fno.ready_for_training

    def test_no_phase4e_data_accessed(self):
        """Verify that GPM cube discovery does not enumerate Phase 4E locked test data."""
        from jalrakshak_ml.flood.gpm_to_forcing import discover_gpm_cubes
        cubes = discover_gpm_cubes()
        for cube in cubes:
            assert "locked" not in str(cube).lower()
            assert "test_phase4e" not in str(cube).lower()
            assert "replay" not in str(cube).lower() or "gfs_replay" in str(cube)
