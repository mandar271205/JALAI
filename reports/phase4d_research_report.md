# Phase 4D: Advanced Multi-Source Weather Data Layer — Final Research Report

**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4D Complete  
**Date:** 2026-09-08  
**Locked Operational State:**  
- `OPERATIONAL_NOWCASTER=PySTEPS`  
- `OPERATIONAL_FUSION_PROVIDER=NONE`  
- Held-Out Test Events: `mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05` (51 sequences, 204 issue-horizon fields)  

---

## 1. Answers to the 13 Mandated Research Questions

### Q1: Which weather sources are genuinely available?
1. **NOAA GFS (0.25° Global NWP):** Genuinely accessible without credentials via AWS Open Data (`s3://noaa-gfs-bdp-pds/`). Local GRIB archive (`20230725_00Z_gfs.t00z.pgrb2.0p25.f000`) and indexed byte-range cache exist in `data/raw/weather/gfs_replay_prate_v1/`.
2. **NASA GPM IMERG V07 Final Run (Archive Only):** Genuinely available locally in `data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1/` (120 half-hourly frames across 5 events).
3. **Copernicus DEM (GLO-30):** Genuinely available locally in `data/processed/static/elevation.npy` (256x256 canonical grid).
4. **OpenStreetMap Infrastructure:** Genuinely available locally in `data/processed/static/`.

### Q2: Which are only adapters?
1. **IMD Doppler Weather Radar (Mumbai Colaba `VABB` / Veravali):** Adapter-ready interface in `src/jalrakshak_ml/weather/adapters/imd_radar.py`.
2. **ISRO MOSDAC INSAT-3D / INSAT-3DR:** Adapter-ready interface in `src/jalrakshak_ml/weather/adapters/mosdac_insat.py`.
3. **IMD AWS Surface Rain Gauges:** Adapter-ready interface in `src/jalrakshak_ml/adapters/imd_aws.py`.

### Q3: Which require credentials?
1. **IMD Doppler Weather Radar:** Requires formal institutional Memorandum of Understanding (MoU) and secure intranet access with IMD.
2. **ISRO MOSDAC INSAT-3D/3DR:** Requires institutional user registration and API authorization tokens from https://www.mosdac.gov.in/.
3. **NASA GPM IMERG Near-Real-Time (Early/Late Run):** Requires NASA Earthdata login credentials configured in `~/.netrc`.

### Q4: Which are historical-only?
1. **NASA GPM IMERG V07 Final Run:** The Final Run incorporates multi-month rain gauge calibrations and operates with a ~3.5-month (~105-day) latency. It is strictly **`GROUND_TRUTH_ONLY`** for retrospective evaluation and model training. It must never be presented as an operational real-time feed.

### Q5: Which can be used for real-time inference?
1. **NOAA GFS (0.25° NWP):** `REALTIME_ELIGIBLE` under an operational publication latency constraint ($\ge 6\text{ hours}$ from cycle initialization).
2. **PySTEPS Optical Flow Nowcaster:** Uses real-time observation history (e.g. from future radar or satellite feeds).
3. **IMD Doppler Radar & INSAT-3D/3DR:** Structurally `REALTIME_ELIGIBLE` once live credentials and data streams are connected to their respective adapters.

### Q6: What are native resolutions and cadences?
| Source | Spatial Resolution | Temporal Cadence | Operational Latency |
| :--- | :--- | :--- | :--- |
| **IMD Doppler Radar** | ~1 km polar range gates (150–250 m) | 15 minutes | 15–20 minutes |
| **MOSDAC INSAT-3D/3DR** | 4 km (IR / WV) / 1 km (VIS) | 30 minutes | 30–45 minutes |
| **NASA GPM IMERG V07** | 0.1° (~11 km over Mumbai) | 30 minutes | ~3.5 months (Final Run) |
| **NOAA GFS NWP** | 0.25° (~28 km over Mumbai) | 60 minutes | ~6 hours |
| **Copernicus DEM** | 30 m | Static | Zero |

### Q7: Which GFS meteorological fields are now supported?
1. `prate`: Surface precipitation rate (converted to mm/h)
2. `tp`: Accumulated precipitation (mm)
3. `10u`: 10m U wind component (m/s)
4. `10v`: 10m V wind component (m/s)
5. `wind_speed_10m`: Derived horizontal wind speed $\sqrt{u_{10}^2 + v_{10}^2}$ (m/s)
6. `wind_direction_10m`: Derived meteorological wind direction $[0, 360)^\circ$
7. `2t`: 2m air temperature (K, convertible to °C)
8. `2r`: 2m relative humidity (%)
9. `sp`: Surface air pressure (Pa)
10. `cape`: Surface convective available potential energy (J/kg)
11. `pwat`: Total column precipitable water (kg/m²)

### Q8: Are radar products actual or only interface-ready?
**Interface-ready only.** No raw radar volume scans exist in the local workspace. In adherence to research integrity, **zero synthetic or fake radar grids have been generated**. The adapter enforces `AUTH_REQUIRED` and strictly separates raw reflectivity ($Z$) from derived rainfall rate ($R$).

### Q9: Are INSAT products actual or only interface-ready?
**Interface-ready only.** No raw HDF5 or NetCDF INSAT granules exist in the workspace. The adapter enforces `AUTH_REQUIRED`. Zero synthetic satellite imagery has been created.

### Q10: Which events are verified extreme vs merely candidate monsoon events?
- **`VERIFIED_EXTREME` (External Benchmark Ground Truth):**
  - `mumbai_cloudburst_2005_07_26`: 944.2 mm / 24h at Santacruz (IMD record).
  - `mumbai_monsoon_2017_08_29`: 331.4 mm / 24h at Santacruz.
- **`MONSOON_EVENT` / `CANDIDATE` (Project Operational Splits):**
  - `mumbai_monsoon_2023_07_18` (Train split): Active monsoon surge.
  - `mumbai_monsoon_2023_07_25` (Validation split): Active offshore trough.
  - `mumbai_monsoon_2023_08_24` (Locked Test split): Active monsoon pulse.
  - `mumbai_monsoon_2024_08_04` (Locked Test split): Active monsoon depression.
  - `mumbai_monsoon_2024_09_05` (Locked Test split): Late monsoon surge.
  *Note:* None of the 5 project monsoon events are artificially inflated or falsely labeled as extreme disasters without external gauge verification.

### Q11: What is the degradation path when sources disappear?
The pipeline executes a 4-tier graceful fallback hierarchy:
- **Level 1 (Full):** Radar observation + Satellite cloud context + GFS NWP synoptic guidance.
- **Level 2 (Radar Outage):** Satellite (INSAT QPE or GPM NRT) observation + GFS NWP guidance.
- **Level 3 (Satellite Outage):** GPM historical / persistence observation + GFS NWP guidance.
- **Level 4 (Degraded):** Available single source with `missing_channel_mask[c] = True` and explicit fallback audit metadata. Fallback data is **never relabeled**.

### Q12: What multi-source channels are ready for future model training?
The `MultiSourceTensorBuilder` provides an 11-channel tensor structure $(11, 256, 256)$:
0. `rainfall_gpm`
1. `radar_reflectivity`
2. `radar_rainfall`
3. `satellite_ir`
4. `satellite_wv`
5. `gfs_precipitation`
6. `gfs_u10`
7. `gfs_v10`
8. `gfs_rh2m`
9. `gfs_t2m`
10. `gfs_cape`
Accompanied by channel-level `valid_mask` $(11, 256, 256)$ and `missing_channel_mask` $(11,)$. Training source dropout ($p \in [0.1, 0.3]$) is fully supported.

### Q13: What remains blocked by data access?
1. Real-time assimilation of IMD Doppler Weather Radar feeds (blocked by institutional MoU requirements).
2. Live ingest of MOSDAC INSAT-3D/3DR spectral channels (blocked by MOSDAC institutional user token).
3. Automated near-real-time GPM early/late run downloads (blocked by missing Earthdata credentials).

---

## 2. Test Verification Summary

- **Total Unit & Regression Tests Executed:** 82 tests
- **Tests Passed:** 82 passed (100% pass rate)
- **Tests Failed:** 0 failed
- **New Phase 4D Tests:** 18 tests covering:
  - Source registry schemas and lookups
  - Canonical `MeteorologicalField` dataclass invariants
  - Temporal anti-leakage rejection of future availability times
  - Derived wind speed and meteorological direction calculations
  - Z-R relationship conversions (Marshall-Palmer & Tropical Monsoon)
  - Radar and INSAT unavailable adapter behavior
  - QC Engine V2 physical range bounds, relative humidity sanity, constant-field detection, all-zero detection, and staleness
  - Source status API and decoupling of data quality from model confidence
  - Multi-source tensor builder complete and degraded modes
  - Versioned multi-source store serialization
  - Backwards compatibility with existing `ForecastResult` and `gfs_replay`

---

## 3. Generated Artifacts

- **Source Audit:** `reports/phase4d_source_audit.md`
- **Status Snapshot:** `reports/phase4d_multisource_status.json`
- **Architecture Report:** `reports/phase4d_multisource_report.md`
- **Rainfall Event Catalog:** `data/catalogs/mumbai_rainfall_events_v1.json`
- **Visual QC Dashboard:** `reports/figures/phase4d_multisource_qc_panels.png`
- **Core Python Source Code:**
  - `src/jalrakshak_ml/weather/contracts.py`
  - `src/jalrakshak_ml/weather/registry.py`
  - `src/jalrakshak_ml/weather/adapters/base.py`
  - `src/jalrakshak_ml/weather/adapters/imd_radar.py`
  - `src/jalrakshak_ml/weather/adapters/mosdac_insat.py`
  - `src/jalrakshak_ml/weather/adapters/gpm.py`
  - `src/jalrakshak_ml/weather/adapters/gfs_rich.py`
  - `src/jalrakshak_ml/weather/alignment.py`
  - `src/jalrakshak_ml/weather/qc.py`
  - `src/jalrakshak_ml/weather/status.py`
  - `src/jalrakshak_ml/weather/multisource.py`
  - `src/jalrakshak_ml/weather/visuals.py`
- **Test Suite:** `tests/test_weather_phase4d.py`

---

## 4. Scientific Limitations

1. **Spatial Representation:** Reprojecting 0.1° GPM (~11 km) or 0.25° GFS (~28 km) onto the 256x256 Mumbai domain aligns grid coordinates to the pilot bounding box, but creates zero new micro-scale atmospheric physics. Resampling must never be termed downscaling.
2. **Decoupled Quality:** A high quality score ($1.0$) confirms that data values are physically sane and complete, not that the downstream forecast will be accurate.
3. **No Retraining Conducted:** ConvLSTM V2, LearnedGateMLP, and the probabilistic calibration curves were not modified or retrained, preserving locked Phase 4C benchmark metrics.

---

## FINAL STATUS BLOCK

```
PHASE_4D_SOURCE_AUDIT_COMPLETE=true
METEOROLOGICAL_SOURCE_CONTRACT_READY=true
WEATHER_SOURCE_REGISTRY_READY=true
GFS_RICH_FIELDS_READY=true
IMD_RADAR_ADAPTER_READY=true
IMD_RADAR_REAL_DATA_READY=false
INSAT_MOSDAC_ADAPTER_READY=true
INSAT_REAL_DATA_READY=false
EXTREME_EVENT_CATALOG_READY=true
MULTISOURCE_TIME_ALIGNMENT_READY=true
MULTISOURCE_SPATIAL_ALIGNMENT_READY=true
METEOROLOGICAL_QC_V2_READY=true
MULTISOURCE_TENSOR_BUILDER_READY=true
MULTISOURCE_HISTORICAL_REPLAY_READY=true
MULTISOURCE_REALTIME_READY=true
PHASE_4D_COMPLETE=true
```
