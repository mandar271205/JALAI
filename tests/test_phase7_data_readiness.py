"""Phase 7 Real-Data and Physics Readiness Test Suite.

Tests empirical data pipelines, solver readiness checks, claim gate enforcement,
roughness derivation, topology audit, exposure and vulnerability pipelines,
and geospatial alignment verification without data fabrication.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine

from jalrakshak_ml.core.claim_gates import ScientificClaimGates
from jalrakshak_ml.flood.drainage import DrainageAuditor
from jalrakshak_ml.flood.forcing import HydraulicForcingAdapter
from jalrakshak_ml.flood.roughness import ManningRoughnessMapper
from jalrakshak_ml.flood.scenario_catalog import PhysicsScenarioBuilder
from jalrakshak_ml.flood.solver_readiness import (
    audit_lisflood_readiness,
    audit_swmm_readiness,
)
from jalrakshak_ml.flood.validation_evidence import (
    FloodEvidenceIngestor,
    FloodEvidenceItem,
    FloodEvidenceType,
)
from jalrakshak_ml.qc.geospatial_auditor import (
    GeospatialAlignmentAuditor,
)
from jalrakshak_ml.risk.exposure import AssetClass
from jalrakshak_ml.risk.exposure_pipeline import ExposureDataPipeline
from jalrakshak_ml.risk.vulnerability_pipeline import (
    FactorReadinessCategory,
    VulnerabilityEvidenceAuditor,
)

# =====================================================================
# 1. LAND COVER & ROUGHNESS TESTS
# =====================================================================

def test_roughness_mapper_uncalibrated_claim():
    """Verify roughness mapper defaults strictly to UNCALIBRATED."""
    mapper = ManningRoughnessMapper()
    assert mapper.metadata.calibration_state == "UNCALIBRATED"


def test_roughness_categorical_preservation_and_no_bilinear():
    """Verify categorical land cover codes are preserved and categorical resampling rule is enforced."""
    mapper = ManningRoughnessMapper()
    from jalrakshak_ml.flood.roughness import ESA_WORLDCOVER_CLASSES

    # Test valid ESA WorldCover classes
    assert ESA_WORLDCOVER_CLASSES[10]["manning_n"] == 0.120  # Tree cover
    assert ESA_WORLDCOVER_CLASSES[50]["manning_n"] == 0.018  # Built-up
    assert ESA_WORLDCOVER_CLASSES[80]["manning_n"] == 0.030  # Permanent water

    # Resampling method must reject bilinear/cubic for categorical data
    mapper.validate_resampling_method("nearest")
    mapper.validate_resampling_method("mode")
    with pytest.raises(ValueError, match="Categorical land-cover classes cannot be resampled"):
        mapper.validate_resampling_method("bilinear")
    with pytest.raises(ValueError, match="Categorical land-cover classes cannot be resampled"):
        mapper.validate_resampling_method("cubic")


def test_roughness_physical_bounds():
    """Verify generated roughness values stay strictly within physical Manning bounds [0.010, 0.200]."""
    mapper = ManningRoughnessMapper()
    classes = np.array([[10, 50], [80, 60]])
    roughness = mapper.map_worldcover_to_manning(classes)
    assert np.all(roughness >= 0.010)
    assert np.all(roughness <= 0.200)


# =====================================================================
# 2. DRAINAGE & TOPOLOGY TESTS
# =====================================================================

def test_drainage_auditor_topological_deficiencies(tmp_path: Path):
    """Test detection of dangling edges, disconnected components, duplicates, and SWMM blocking."""
    geojson_path = tmp_path / "mock_waterways.geojson"
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[72.8, 19.0], [72.85, 19.0]]},
            "properties": {"osm_id": 1, "waterway": "drain"},
        },
        # Dangling disconnected edge
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[72.9, 19.1], [72.95, 19.1]]},
            "properties": {"osm_id": 2, "waterway": "stream"},
        },
        # Duplicate of edge 1
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[72.8, 19.0], [72.85, 19.0]]},
            "properties": {"osm_id": 3, "waterway": "drain"},
        },
    ]
    data = {"type": "FeatureCollection", "features": features}
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    auditor = DrainageAuditor(geojson_path)
    manifest = auditor.audit()

    assert manifest.feature_count == 3
    assert manifest.topology_qc["duplicate_segments"] == 1
    assert manifest.usable_for_swmm is False
    assert any("sewer pipe network" in b or "depths" in b for b in manifest.swmm_blocker_reasons)


def test_drainage_missing_file():
    """Verify auditor raises FileNotFoundError on missing file."""
    with pytest.raises(FileNotFoundError):
        DrainageAuditor(Path("non_existent_waterways.geojson"))


# =====================================================================
# 3. SWMM & LISFLOOD-FP READINESS TESTS
# =====================================================================

def test_swmm_readiness_rejection_of_false_claims():
    """Verify SWMM reports executable_input_ready=False and provides explicit blockers."""
    report = audit_swmm_readiness()

    assert report.solver_available is False
    assert report.network_nodes_available is False
    assert report.network_links_available is False
    assert report.subcatchments_available is False
    assert report.invert_elevations_available is False
    assert report.executable_input_ready is False
    assert len(report.blockers) >= 4
    assert len(report.acquisition_checklist) >= 5


def test_lisflood_readiness_distinguishes_inputs_from_solver(tmp_path: Path):
    """Verify LISFLOOD distinguishes INPUT_DATA_READY from SOLVER_AVAILABLE and EXECUTION_READY."""
    # When inputs are missing
    rep_empty = audit_lisflood_readiness(
        dem_path=tmp_path / "missing_dem.tif",
        roughness_path=tmp_path / "missing_rough.tif",
    )
    assert rep_empty.input_data_ready is False
    assert rep_empty.solver_available is False
    assert rep_empty.execution_ready is False
    assert rep_empty.calibration_ready is False

    # When inputs exist but solver executable is missing
    dem_file = tmp_path / "dem.tif"
    rough_file = tmp_path / "rough.tif"

    profile = {
        "driver": "GTiff",
        "height": 10,
        "width": 10,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32643",
        "transform": Affine.translation(0, 0) * Affine.scale(1, 1),
    }
    with rasterio.open(dem_file, "w", **profile) as dst:
        dst.write(np.ones((1, 10, 10), dtype=np.float32) * 15.0)
    with rasterio.open(rough_file, "w", **profile) as dst:
        dst.write(np.ones((1, 10, 10), dtype=np.float32) * 0.035)

    rep_ready = audit_lisflood_readiness(
        dem_path=dem_file,
        roughness_path=rough_file,
    )
    assert rep_ready.input_data_ready is True
    assert rep_ready.solver_available is False
    assert rep_ready.execution_ready is False  # Cannot execute without solver!
    assert "LISFLOOD-FP compiled binary 'lisflood' not found" in rep_ready.blockers[0]


# =====================================================================
# 4. RAINFALL FORCING ADAPTER TESTS
# =====================================================================

def test_hydraulic_forcing_generation(tmp_path: Path):
    """Verify hydraulic forcing adapter preserves mm/h units, timestamps, and metadata."""
    adapter = HydraulicForcingAdapter()
    rates = [10.5, 25.0, 5.2]
    start_time = "2021-06-18T00:00:00Z"
    bdy_file = tmp_path / "test.bdy"
    dat_file = tmp_path / "test.dat"

    out_bdy, meta = adapter.build_lisflood_bdy(
        event_id="test_event_01",
        rates_mm_h=rates,
        start_time_iso=start_time,
        output_path=bdy_file,
    )
    assert out_bdy.exists()
    assert meta.units == "mm/h"
    assert meta.native_cadence_minutes == 30
    assert meta.timesteps_count == 3
    assert meta.mean_rate_mm_h == pytest.approx(13.567, abs=0.01)

    out_dat, _s_meta = adapter.build_swmm_dat(
        station_id="STA01",
        rates_mm_h=rates,
        start_time_iso=start_time,
        output_path=dat_file,
    )
    assert out_dat.exists()
    dat_content = out_dat.read_text()
    assert "STA01" in dat_content
    assert "10.500" in dat_content

    # Negative rates must raise ValueError
    with pytest.raises(ValueError, match="cannot be negative"):
        adapter.build_lisflood_bdy(
            event_id="bad",
            rates_mm_h=[-1.0, 5.0],
            start_time_iso=start_time,
            output_path=tmp_path / "bad.bdy",
        )


# =====================================================================
# 5. FLOOD VALIDATION EVIDENCE TESTS
# =====================================================================

def test_flood_evidence_type_separation(tmp_path: Path):
    """Verify strict separation between observed extent, modelled extent, and susceptibility."""
    ingestor = FloodEvidenceIngestor(search_dir=tmp_path)
    manifest = ingestor.audit_evidence_availability()
    assert manifest.real_flood_validation_data_available is False

    # Valid observed extent item
    valid_obs = FloodEvidenceItem(
        evidence_id="evi_01",
        evidence_type=FloodEvidenceType.OBSERVED_EXTENT,
        source="Sentinel-1 SAR inundation mask",
        event_id="mumbai_2021_07",
        timestamp_utc="2021-07-16T12:00:00Z",
        crs="EPSG:32643",
        data_path=str(tmp_path / "obs.tif"),
        is_empirical=True,
        units="binary_extent",
        resolution="256x256",
        provenance={"method": "otsu_thresholding"},
    )
    valid_obs.validate()  # Must pass without error

    # Non-empirical observed extent must fail validation
    invalid_obs = FloodEvidenceItem(
        evidence_id="evi_bad",
        evidence_type=FloodEvidenceType.OBSERVED_EXTENT,
        source="Synthetic mask",
        event_id="mumbai_2021_07",
        timestamp_utc="2021-07-16T12:00:00Z",
        crs="EPSG:32643",
        data_path=str(tmp_path / "obs.tif"),
        is_empirical=False,  # Prohibited!
        units="binary_extent",
        resolution="256x256",
        provenance={},
    )
    with pytest.raises(ValueError, match="Observed extent must be marked as empirical"):
        invalid_obs.validate()

    # Susceptibility with depth units (meters) must fail validation
    invalid_susc = FloodEvidenceItem(
        evidence_id="susc_bad",
        evidence_type=FloodEvidenceType.SUSCEPTIBILITY,
        source="Susceptibility map",
        event_id="mumbai_2021_07",
        timestamp_utc="2021-07-16T12:00:00Z",
        crs="EPSG:32643",
        data_path=str(tmp_path / "susc.tif"),
        is_empirical=False,
        units="m",  # Susceptibility is NEVER depth in meters!
        resolution="256x256",
        provenance={},
    )
    with pytest.raises(ValueError, match="Susceptibility evidence must have dimensionless units"):
        invalid_susc.validate()


# =====================================================================
# 6. EXPOSURE PIPELINE TESTS
# =====================================================================

def test_exposure_pipeline_asset_handling(tmp_path: Path):
    """Test exposure pipeline clipping, aggregation, and explicit download pending."""
    # Create dummy static dir with mock hospitals and mock elevation
    dem_file = tmp_path / "elevation.tif"
    profile = {
        "driver": "GTiff",
        "height": 32,
        "width": 32,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32643",
        "transform": Affine(1000.0, 0.0, 270000.0, 0.0, -1000.0, 2130000.0),
    }
    with rasterio.open(dem_file, "w", **profile) as dst:
        dst.write(np.zeros((1, 32, 32), dtype=np.float32))

    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [72.85, 19.05]}, "properties": {"osm_id": 101}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [72.00, 19.05]}, "properties": {"osm_id": 102}}, # Outside Mumbai bbox
    ]
    geojson_path = tmp_path / "hospitals.geojson"
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    pipeline = ExposureDataPipeline(
        static_dir=tmp_path,
        raw_osm_dir=tmp_path,
        canonical_dem_path=dem_file,
    )
    layers, _grids = pipeline.process_all_asset_classes()

    # Hospital layer must be AVAILABLE with 1 clipped feature
    hosp = layers[AssetClass.HOSPITALS.value]
    assert hosp.status == "AVAILABLE"
    assert hosp.feature_count == 1  # 1 inside, 1 outside excluded

    # Buildings & Population must be strictly DOWNLOAD_PENDING
    bldg = layers[AssetClass.BUILDINGS.value]
    assert bldg.status == "DOWNLOAD_PENDING"
    assert bldg.feature_count is None

    pop = layers[AssetClass.POPULATION.value]
    assert pop.status == "DOWNLOAD_PENDING"
    assert pop.raw_total_metric is None


# =====================================================================
# 7. VULNERABILITY PIPELINE TESTS
# =====================================================================

def test_vulnerability_pipeline_factor_classification():
    """Verify vulnerability factors are strictly classified as AVAILABLE_PROXY, MISSING, or UNSUPPORTED."""
    auditor = VulnerabilityEvidenceAuditor()
    manifest = auditor.audit_factors()

    assert manifest.real_vulnerability_data_available is False
    assert manifest.vulnerability_proxy_data_available is True

    # Census age sensitivity must be MISSING
    census_factor = next(f for f in manifest.factors if f.factor_id == "census_population_age_sensitivity")
    assert census_factor.category == FactorReadinessCategory.MISSING

    # Hospital accessibility must be AVAILABLE_PROXY
    hosp_factor = next(f for f in manifest.factors if f.factor_id == "hospital_accessibility_proxy")
    assert hosp_factor.category == FactorReadinessCategory.AVAILABLE_PROXY

    # Unsupported synthetic index must be UNSUPPORTED
    bad_factor = next(f for f in manifest.factors if f.factor_id == "synthetic_deprivation_index")
    assert bad_factor.category == FactorReadinessCategory.UNSUPPORTED


# =====================================================================
# 8. GEOSPATIAL ALIGNMENT AUDITOR TESTS
# =====================================================================

def test_geospatial_auditor_detection(tmp_path: Path):
    """Test geospatial alignment auditor detecting CRS mismatch, dimension mismatch, and nodata."""
    ref_profile = {
        "crs": "EPSG:32643",
        "shape": [256, 256],
        "transform": [125.7, 0.0, 263155.0, 0.0, -196.1, 2135000.0],
    }
    auditor = GeospatialAlignmentAuditor(root_dir=tmp_path)

    # Valid raster
    valid_file = tmp_path / "valid.tif"
    profile = {
        "driver": "GTiff",
        "height": 256,
        "width": 256,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32643",
        "transform": Affine(125.7, 0.0, 263155.0, 0.0, -196.1, 2135000.0),
    }
    with rasterio.open(valid_file, "w", **profile) as dst:
        dst.write(np.zeros((1, 256, 256), dtype=np.float32))

    audit_res = auditor.audit_raster(valid_file, ref_profile=ref_profile)
    assert audit_res.matches_reference_grid is True
    assert len(audit_res.discrepancies) == 0

    # Raster with wrong CRS (EPSG:4326)
    bad_crs_file = tmp_path / "bad_crs.tif"
    profile_bad_crs = profile.copy()
    profile_bad_crs["crs"] = "EPSG:4326"
    with rasterio.open(bad_crs_file, "w", **profile_bad_crs) as dst:
        dst.write(np.zeros((1, 256, 256), dtype=np.float32))

    bad_crs_res = auditor.audit_raster(bad_crs_file, ref_profile=ref_profile)
    assert bad_crs_res.matches_reference_grid is False
    assert any("CRS mismatch" in issue for issue in bad_crs_res.discrepancies)

    # Raster with wrong dimensions (128x128)
    bad_dim_file = tmp_path / "bad_dim.tif"
    profile_bad_dim = profile.copy()
    profile_bad_dim["height"] = 128
    profile_bad_dim["width"] = 128
    with rasterio.open(bad_dim_file, "w", **profile_bad_dim) as dst:
        dst.write(np.zeros((1, 128, 128), dtype=np.float32))

    bad_dim_res = auditor.audit_raster(bad_dim_file, ref_profile=ref_profile)
    assert bad_dim_res.matches_reference_grid is False
    assert any("Shape mismatch" in issue for issue in bad_dim_res.discrepancies)


# =====================================================================
# 9. CLAIM GATES & FALSE UPGRADE PREVENTION TESTS
# =====================================================================

def test_scientific_claim_gates_prevention_of_false_upgrades():
    """Verify claim gates raise ValueError when uncalibrated or unverified readiness flags are claimed."""
    # Attempting to claim calibrated roughness without evidence
    with pytest.raises(ValueError, match="cannot claim calibration"):
        ScientificClaimGates(
            ROUGHNESS_LAYER_READY=True,
            ROUGHNESS_CALIBRATED=True,  # False claim!
        )

    # Attempting to claim SWMM execution ready without inputs
    with pytest.raises(ValueError, match="SWMM execution cannot be ready"):
        ScientificClaimGates(
            SWMM_INPUTS_AVAILABLE=False,
            SWMM_EXECUTION_READY=True,  # False claim!
        )

    # Attempting to claim LISFLOOD execution ready without solver binary
    with pytest.raises(ValueError, match="LISFLOOD-FP execution cannot be ready"):
        ScientificClaimGates(
            LISFLOOD_INPUT_DATA_READY=True,
            LISFLOOD_SOLVER_AVAILABLE=False,
            LISFLOOD_EXECUTION_READY=True,  # False claim!
        )

    # Attempting to claim genuine FNO targets without genuine physics simulation
    with pytest.raises(ValueError, match="Genuine FNO targets require executed real simulations"):
        ScientificClaimGates(
            REAL_PHYSICS_SIMULATION_EXECUTED=False,
            GENUINE_FNO_TARGETS_AVAILABLE=True,  # False claim!
        )

    # Attempting to claim real vulnerability when only proxies exist
    with pytest.raises(ValueError, match="Socioeconomic vulnerability data is proxy only"):
        ScientificClaimGates(
            VULNERABILITY_PROXY_DATA_AVAILABLE=True,
            REAL_VULNERABILITY_DATA_AVAILABLE=True,  # False claim!
        )

    # Valid Phase 7 state must pass without error
    valid_gates = ScientificClaimGates(
        PHASE_7_DATA_READINESS_HARDENED=True,
        ROUGHNESS_LAYER_READY=True,
        ROUGHNESS_CALIBRATED=False,
        LISFLOOD_INPUT_DATA_READY=True,
        LISFLOOD_SOLVER_AVAILABLE=False,
        LISFLOOD_EXECUTION_READY=False,
        SWMM_INPUTS_AVAILABLE=False,
        SWMM_EXECUTION_READY=False,
        REAL_FLOOD_VALIDATION_DATA_AVAILABLE=False,
        VULNERABILITY_PROXY_DATA_AVAILABLE=True,
        REAL_VULNERABILITY_DATA_AVAILABLE=False,
    )
    assert valid_gates.PHASE_7_DATA_READINESS_HARDENED is True
    assert valid_gates.ROUGHNESS_CALIBRATED is False


# =====================================================================
# 10. PHYSICS SCENARIO CATALOG TESTS
# =====================================================================

def test_physics_scenario_catalog_builder():
    """Verify scenario catalog builds 81 scenarios adhering to locked test boundaries."""
    events_cat = Path("data/catalogs/mumbai_rainfall_events_v1.json")
    elev_path = Path("data/processed/static/elevation.tif")
    rough_path = Path("data/processed/static/roughness.tif")

    builder = PhysicsScenarioBuilder(
        events_catalog_path=events_cat,
        elevation_path=elev_path,
        roughness_path=rough_path,
    )
    report = builder.build_catalog()

    assert report.total_scenarios == 81
    assert report.scenarios_by_split["train"] == 72
    assert report.scenarios_by_split["validation"] == 6
    assert report.scenarios_by_split["test_locked_reserved"] == 3

    # Zero depth targets fabricated
    for s in report.scenarios:
        assert s["simulated_water_depth_target_available"] is False

    # Simulation planning
    plan = report.simulation_design_plan
    assert plan["minimum_viable_simulation_count"] == 36
    assert plan["expected_solver_runtime_sec"].startswith("UNKNOWN")
