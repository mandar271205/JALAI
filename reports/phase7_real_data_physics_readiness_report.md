# Phase 7 Real-Data and Physics Readiness Report

**Project**: JalRakshak AI / SIH26071 ML + Geospatial  
**Phase**: 7 — Genuine Geospatial Data Readiness & Hydraulic Physics Input Preparation  
**Timestamp**: 2026-09-09T19:55:00Z  
**Authoritative Commits Preserved**: `ea498af`, `0de3b81`, `a7aa17d`, `71155a3`  

---

## 1. Current-State Audit

JalRakshak AI has progressed through verified milestones:
- **Phase 4E**: Rich multi-source GFS reanalysis, radar/satellite fusion, and strict train-only normalization fitted on exactly 12 train events (204 issues) with locked-test contamination rejection.
- **Phase 5 & 6**: Scientific framework foundations established (`SUSCEPTIBILITY_IS_NOT_DEPTH=True`, FNO architecture initialized, probabilistic HEV risk engine ready, explainability engine ready, citizen verification heuristics ready).
- **Phase 7 (This Phase)**: Empirical data transition. Transitioning the repository from "engineering framework ready" to "genuine Mumbai geospatial inputs prepared for real flood physics, exposure, vulnerability, and eventual FNO training."

Scientific claim gates enforce that no synthetic, heuristic, or fabricated targets are substituted for genuine physical ground-truth.

---

## 2. Genuine Local Data Discovered

A comprehensive audit of all local datasets across `data/` identified 13 authentic artifacts:

| Dataset ID | Source | Path | Format | CRS | Features / Shape | Vintage |
|---|---|---|---|---|---|---|
| `dem_copernicus_glo30_mumbai` | Copernicus GLO-30 | `data/processed/static/elevation.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2024 |
| `slope_derived_glo30_mumbai` | Derived Horn (1981) | `data/processed/static/slope.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2026-09 |
| `aspect_derived_glo30_mumbai` | Derived Horn (1981) | `data/processed/static/aspect.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2026-09 |
| `curvature_derived_glo30_mumbai` | Derived Zevenbergen-Thorne | `data/processed/static/curvature.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2026-09 |
| `twi_derived_glo30_mumbai` | Derived Topographic Wetness | `data/processed/static/twi.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2026-09 |
| `surface_roughness_composite_v1` | Infrastructure & Land Cover | `data/processed/static/roughness.tif` | GeoTIFF | EPSG:32643 | [256, 256] | 2026-09 |
| `osm_mumbai_waterways_v1` | OpenStreetMap | `data/processed/static/waterways.geojson` | GeoJSON | EPSG:4326 | 1,338 features (901.7 km) | 2026-09 |
| `osm_mumbai_roads_v1` | OpenStreetMap | `data/processed/static/roads.geojson` | GeoJSON | EPSG:4326 | 292,968 features | 2026-09 |
| `osm_mumbai_railways_v1` | OpenStreetMap | `data/processed/static/railways.geojson` | GeoJSON | EPSG:4326 | 2,342 features | 2026-09 |
| `osm_mumbai_hospitals_v1` | OpenStreetMap | `data/processed/static/hospitals.geojson` | GeoJSON | EPSG:4326 | 1,229 features | 2026-09 |
| `osm_mumbai_schools_v1` | OpenStreetMap | `data/processed/static/schools.geojson` | GeoJSON | EPSG:4326 | 944 features | 2026-09 |
| `osm_mumbai_emergency_v1` | OpenStreetMap | `data/processed/static/emergency_assets.geojson` | GeoJSON | EPSG:4326 | 2,486 features | 2026-09 |
| `rainfall_events_catalog_v1` | GPM IMERG V07 / GFS | `data/catalogs/mumbai_rainfall_events_v1.json`| JSON | EPSG:4326 | 18 events (12 tr, 3 val, 3 te)| 2026-09 |

---

## 3. Missing Genuine Datasets

The following essential primary datasets are **NOT present** in the local repository and must be acquired before physical simulation and true socioeconomic risk modeling can execute:

1. **Brihanmumbai Municipal Corporation (BMC) Storm Water Drains (SWD) GIS**: Underground conduits, closed pipes, arch drains, and nullahs.
2. **Manhole & Junction Survey Levels**: Invert depths, ground rim elevations, drop junctions.
3. **Pumping Station Discharge & Sump Water Level Logs**: Love Grove, Cleveland Bunder, Britannia, Irla, Haji Ali, Gazdarband stations.
4. **Primary Census of India Ward Demographics**: Age dependency ratios (children <5, elderly >65), disability index.
5. **BMC Property Tax Structural Survey**: Kaccha / Semi-Pucca / Pucca classifications, building plinth heights, basement presence.
6. **Empirical Satellite SAR Flood Extent**: Sentinel-1 SAR water masks for historical monsoon events.
7. **Official Municipal Inundation Incident Logs**: Emergency Operations Centre (Disaster Management Cell) geotagged waterlogging records.
8. **High-Resolution Gridded Population**: WorldPop / GHS-POP 100m raster clipped to Mumbai domain.

---

## 4. Exposure Readiness

The exposure pipeline (`src/jalrakshak_ml/risk/exposure_pipeline.py`) processes 8 asset classes:
- **Available from OSM (6 classes)**: Hospitals (1,229 features), Schools (944 features), Emergency Facilities (2,486 features), Transport Assets (2,342 features), Critical Infrastructure (3,218 features), and Roads (292,968 features).
- **Download Pending (2 classes)**: Buildings (un-downloaded vector footprint polygon dataset) and Population (un-downloaded 100m raster).
- **Integrity Policy**:
  - OSM crowdsourced features are explicitly documented as non-exhaustive (missing tags do not imply non-existence).
  - Both raw metric totals (counts, lengths) and normalized [0, 1] exposure scores are strictly preserved.
  - Zero synthetic population or buildings were fabricated.

---

## 5. Population Readiness

- **Status**: `GENUINE_POPULATION_DATA_AVAILABLE=False`
- **Adapter State**: Marked `DOWNLOAD_PENDING=True` with explicit download endpoints for WorldPop (`IND_ppp_2020_UNadj_constrained.tif`) and Meta High Resolution Settlement Layer (HRSL).
- **Scientific Integrity**: Under no circumstances will uniform, random, or heuristic synthetic population grids be generated. Until an open population raster is downloaded and verified by SHA256, population counts remain `None`.

---

## 6. Land Cover Readiness

- **Lookup Table**: ESA WorldCover 11-class mapping with literature-derived Manning's $n$ parameters (Chow, 1959; Arcement & Schneider, 1989).
- **Resampling Policy**: Categorical land cover must use `nearest` or `mode` resampling. Bilinear, bicubic, and average interpolation are strictly rejected to prevent fractional class creation.
- **Physical Bounds**: Manning's $n$ values are constrained to $[0.010, 0.200]\,\text{s/m}^{1/3}$.

---

## 7. Roughness Readiness

- **Output Artifact**: `data/processed/static/roughness.tif` (256x256, EPSG:32643).
- **Composite Formulation**:
  - Road corridors: $n = 0.015\,\text{s/m}^{1/3}$ (smooth asphalt/pavement)
  - Railway corridors: $n = 0.025\,\text{s/m}^{1/3}$ (ballast and steel track)
  - Waterways / canals: $n = 0.035\,\text{s/m}^{1/3}$ (open alluvial channel)
  - Background terrain: $n = 0.040\,\text{s/m}^{1/3}$ (mixed urban residential)
- **Calibration Status**: Defaults strictly to `UNCALIBRATED`. Claiming calibration without gauged hydrograph stage data is prevented by claim gates.

---

## 8. Drainage Evidence

- **Vector Network**: `data/processed/static/waterways.geojson` (1,338 features, 901.72 km).
- **Topological QC**:
  - Endpoints: 1,803
  - Junction nodes: 823
  - Dangling ends: 1,514
  - Duplicate segments detected: 3
  - Invalid geometries: 0
- **SWMM Usability**: `usable_for_swmm=False`. Crowdsourced surface waterways lack pipe diameters, invert depths, manhole rim elevations, and closed network connectivity.

---

## 9. SWMM Blockers & Readiness

- **Readiness Report**: `reports/phase7_swmm_readiness_report.json`
- **Statuses**:
  - `SWMM_INPUTS_AVAILABLE=False`
  - `SWMM_EXECUTION_READY=False`
- **Blockers**:
  1. Subterranean closed storm sewer GIS absent from local repository.
  2. Conduit diameters, pipe materials, slopes, and box drain geometries unmapped.
  3. Manhole rim elevations and invert depths uncharacterized.
  4. Tidal flap gate discharge coefficients along Mithi River and Mahim Creek unmapped.
  5. SWMM 5.2 solver binary not available on system PATH.

---

## 10. LISFLOOD-FP Blockers & Readiness

- **Readiness Report**: `reports/phase7_lisflood_readiness_report.json`
- **Statuses**:
  - `LISFLOOD_INPUT_DATA_READY=True` (Copernicus DEM 30m + Manning roughness + GPM hyetograph ready)
  - `LISFLOOD_SOLVER_AVAILABLE=False` (Compiled solver binary absent from system PATH; requires Linux container)
  - `LISFLOOD_EXECUTION_READY=False` (Cannot execute without solver binary)
  - `LISFLOOD_CALIBRATION_READY=False` (Uncalibrated literature parameterization)

---

## 11. Rainfall Forcing Readiness

- **Adapter**: `src/jalrakshak_ml/flood/forcing.py`
- **Semantics**: Preserves native mm/h units and 30-minute temporal cadence from GPM IMERG V07.
- **Forcing Artifacts Generated**:
  - `data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.bdy` (LISFLOOD boundary time series)
  - `data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.dat` (SWMM external rain gage time series)
  - `data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.json` (Traceable metadata and SHA256 hash)

---

## 12. Flood Validation Evidence Readiness

- **Framework**: `src/jalrakshak_ml/flood/validation_evidence.py`
- **Categorical Separation**:
  - `observed_extent`: Empirical satellite SAR / optical water delineation
  - `reported_location`: Verified field or citizen waterlogging incident point
  - `modelled_extent`: Numerical hydraulic solver inundation extent
  - `susceptibility`: Dimensionless multi-criteria terrain index $[0, 1]$
  - `hydraulic_depth`: Continuous physical water depth in metres $[0, 10]\,\text{m}$
- **Current Status**: `REAL_FLOOD_VALIDATION_DATA_AVAILABLE=False`. Susceptibility is strictly rejected as ground truth.

---

## 13. Vulnerability Evidence Readiness

- **Framework**: `src/jalrakshak_ml/risk/vulnerability_pipeline.py`
- **Factor Classification**:
  - `AVAILABLE_PROXY` (4 factors): Hospital accessibility proxy (0.25), Road evacuation accessibility proxy (0.25), Emergency facility accessibility proxy (0.20), Settlement density proxy (0.30).
  - `MISSING` (3 factors): Census population age sensitivity, Building structural survey, Ward socioeconomic deprivation index.
  - `UNSUPPORTED` (1 factor): Fabricated synthetic deprivation indices (strictly prohibited).
- **Statuses**: `REAL_VULNERABILITY_DATA_AVAILABLE=False`, `VULNERABILITY_PROXY_DATA_AVAILABLE=True`.

---

## 14. Geospatial Alignment QC

- **Auditor**: `src/jalrakshak_ml/qc/geospatial_auditor.py`
- **Reference Grid**:
  - CRS: Projected UTM Zone 43N (`EPSG:32643`)
  - Dimensions: $256 \times 256$ pixels
  - Cell Resolution: $125.7\,\text{m} \times 196.1\,\text{m}$
  - Bounding Box: $[72.75, 18.85, 73.05, 19.30]$ WGS84
- **Audit Result**: All 6 static rasters (`elevation.tif`, `slope.tif`, `aspect.tif`, `curvature.tif`, `twi.tif`, `roughness.tif`) match the reference grid CRS, pixel dimensions, affine geotransform, and nodata conventions with zero misalignment.

---

## 15. Scenario Catalog

- **Artifact**: `reports/phase7_physics_scenario_catalog.json`
- **Total Scenarios**: 81 reproducible scenarios
  - Train: 72 scenarios (12 locked train events $\times$ 6 perturbation families)
  - Validation: 6 scenarios (3 locked validation events $\times$ 2 perturbation families)
  - Test: 3 scenarios (3 locked test events $\times$ 1 baseline only, strictly reserved for blind evaluation)
- **Perturbations**: Baseline, Heavy Rain Surge ($1.25\times$), Moderate Rain Attenuation ($0.80\times$), High Roughness Vegetated ($1.20\times$), Low Roughness Cleared ($0.85\times$), Pre-Saturated Antecedent Soil.
- **Targets**: `simulated_water_depth_target_available=False` across all 81 scenarios.

---

## 16. Future Physics Simulation Design

- **Minimum Viable Simulations**: 36 runs (covering core baseline + extreme hyetographs across all 12 train events).
- **Preferred Research-Grade Simulations**: 81-120 runs.
- **Split Strategy**: Event-level strict temporal holdout. Zero leakage between train, validation, and locked test events.
- **Storage Planning**:
  - Per simulation output: ~32 MB (256x256 float32 $\times$ 24 hourly time steps, compressed Zarr/NetCDF).
  - Minimum storage requirement: ~1.1 GB.
  - Preferred research-grade storage requirement: ~2.5 to 5.0 GB.
- **Solver Runtime**: Explicitly recorded as `UNKNOWN (Must be benchmarked on target execution hardware)`. Runtime will NOT be fabricated.

---

## 17. FNO Data-Readiness Consequences

- **Threshold for Defensibility**: Fourier Neural Operators map continuous spatial-temporal function spaces (hyetograph $\to$ 2D shallow water flow). At least 70 to 100 genuine numerical simulations satisfying Saint-Venant momentum and continuity equations are required before FNO training is scientifically valid.
- **Strict Prohibition**: Training FNO on static terrain susceptibility maps or heuristic flood proxies is physically meaningless and strictly prohibited.
- **Gate Status**: `GENUINE_FNO_TARGETS_AVAILABLE=False`, `FNO_TRAINING_STARTED=False`.

---

## 18. Tests and Validation

- **New Test Suite**: `tests/test_phase7_data_readiness.py`
  - 14 tests covering: roughness uncalibrated claim, categorical resampling preservation, physical bounds, drainage topology QC, SWMM rejection, LISFLOOD input vs. solver separation, rainfall forcing adapters, flood evidence separation, exposure asset pipeline, vulnerability classification, geospatial alignment auditor, claim gate false-upgrade prevention, scenario catalog builder.
  - Result: **14 / 14 PASSED** (0 failures).
- **Regression Test Suite**: `tests/test_flood_intelligence_pipeline.py`
  - 16 tests covering Phase 5 and Phase 6 modules.
  - Result: **16 / 16 PASSED** (0 failures).
- **Code Quality**:
  - `python -m compileall src scripts tests`: Exit code 0 (all bytecode compiled cleanly).
  - `ruff check`: All Phase 7 modules and scripts passed with 0 errors.

---

## 19. Scientific Limitations

1. **Topography**: Copernicus GLO-30 reflects a 30m DSM smoothed to ~160m on the working grid; micro-topographic street curbs, flyovers, and drainage ditches are sub-grid features.
2. **Subsurface Hydraulics**: Mumbai's flood dynamics are dominated by subterranean storm drains and tidal outfall conditions along Mahim Creek and the Mithi River. Surface 2D overland flow alone cannot simulate surcharging manholes without SWMM 1D conduit integration.
3. **Roughness**: Literature-derived Manning's $n$ values are uncalibrated engineering assumptions.
4. **Vulnerability**: In the absence of Census ward records, vulnerability scores are spatial distance proxies and do not reflect household income or informal settlement resilience.

---

## 20. Exact Next Execution Steps

1. **Containerized Hydraulic Simulation**:
   - Build a Docker container containing compiled LISFLOOD-FP 8.x / EPA-SWMM 5.2 binaries.
   - Run the 36 minimum viable simulation scenarios using the forcing files generated in `data/processed/flood/forcing/`.
   - Record actual wall-clock execution runtimes to replace `UNKNOWN`.
2. **Data Acquisition**:
   - Download WorldPop India 100m population raster and clip to Mumbai bounding box.
   - Ingest OpenStreetMap building footprints polygon GeoJSON.
   - Request BMC SWD GIS conduits and pumping station pump logs.
3. **Validation Collection**:
   - Download historical Sentinel-1 SAR GRD scenes for Mumbai monsoon flood dates (e.g. July 2021, July 2023) and generate binary water masks.
4. **Fourier Neural Operator (FNO) Surrogate Training**:
   - Once genuine LISFLOOD-FP 2D simulation output NetCDF/Zarr files exceed 70 runs, assemble the spatial-temporal tensor dataset.
   - Train the 2D FNO surrogate on genuine physics targets.
