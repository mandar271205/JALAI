# Phase 4D: Multi-Source Meteorological Data Architecture & Availability Report

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4D Multi-Source Weather Layer  
**Operational Nowcaster:** PySTEPS (Locked Winner)  
**Operational Fusion Provider:** NONE  

---

## 1. Executive Summary

Phase 4D establishes the canonical meteorological data layer for the JalRakshak AI pipeline. This system provides a unified, strongly-typed interface (`MeteorologicalField`) across heterogeneous observational and numerical weather prediction (NWP) sources, while upholding strict scientific principles:
1. **Zero Data Fabrication:** No fake radar scans or synthetic satellite imagery are created. Unavailable sources are honestly reported as `AUTH_REQUIRED` or `UNAVAILABLE`.
2. **Decoupling of Critical Concepts:**
   - **Availability:** Is the data available as of the simulated forecast issue time without future temporal leakage?
   - **Data Quality:** Is the physical observation sane, uncorrupted, and complete ($\text{quality\_score} \in [0, 1]$)?
   - **Model Confidence:** What is the predictive certainty of downstream models ($\text{forecast\_confidence} \in [0, 1]$)?
3. **No False Resolution Claims:** Reprojection to the canonical 256x256 Mumbai grid (EPSG:32643) is spatial alignment, **never physical downscaling**. Native resolutions (0.1° for GPM, 0.25° for GFS, ~1 km for Radar, 4 km for INSAT) are strictly tracked in provenance.
4. **Ground Truth vs. Real-Time Separation:** NASA GPM IMERG V07 Final Run is strictly tagged `GROUND_TRUTH_ONLY` due to its ~3.5-month latency. NOAA GFS is `REALTIME_ELIGIBLE` under an enforced 6-hour operational publication latency.

---

## 2. Multi-Source Status & Capability Breakdown

### 2.1 Available Now
- **NOAA GFS (0.25° Global NWP):**
  - **Provider:** NOAA NCEP via AWS Open Data (`s3://noaa-gfs-bdp-pds/`).
  - **Authentication:** None required.
  - **Latency:** 5.5 to 6.0 hours from cycle initialization (strictly enforced).
  - **Variables Supported & Decoded:**
    - `prate`: Surface precipitation rate (avg over interval, converted to mm/h)
    - `tp`: Total accumulated precipitation (accum over interval, mm)
    - `10u`: 10m U wind component (m/s)
    - `10v`: 10m V wind component (m/s)
    - `wind_speed_10m`: Derived $\sqrt{u_{10}^2 + v_{10}^2}$ (m/s)
    - `wind_direction_10m`: Derived meteorological wind direction ($[0, 360)^\circ$)
    - `2t`: 2m air temperature (K, convertible to °C)
    - `2r`: 2m relative humidity (%)
    - `sp`: Surface air pressure (Pa)
    - `cape`: Surface convective available potential energy (J/kg)
    - `pwat`: Precipitable water in entire atmospheric column (kg/m²)

### 2.2 Archive-Ready
- **NASA GPM IMERG V07 (Final Run):**
  - **Provider:** NASA GES DISC.
  - **Local Corpus:** 120 processed half-hourly frames across 5 monsoon episodes (Train: `2023_07_18`, Validation: `2023_07_25`, Test: `2023_08_24`, `2024_08_04`, `2024_09_05`).
  - **Role:** Canonical training ground truth and benchmark evaluation.
  - **Status:** Archive-ready; prohibited from live operational nowcasting due to 3.5-month post-processing latency.
- **Copernicus DEM (GLO-30):**
  - Static 30m topographic foundation processed to canonical grid in `data/processed/static/elevation.npy`.
- **OpenStreetMap (OSM) Infrastructure:**
  - Critical asset and vulnerability layers in `data/processed/static/`.

### 2.3 Adapter-Ready
- **IMD Doppler Weather Radar (Mumbai Colaba / Veravali):**
  - **Adapter Class:** `jalrakshak_ml.weather.adapters.imd_radar.IMDRadarAdapter`
  - **Architecture:** Supports station metadata (`VABB`), scan geometry, Cartesian rasterization scaffold, and explicit Z-R conversion models (`marshall_palmer`, `tropical_monsoon`, `deep_convection`).
  - **Integrity Rule:** Reflectivity ($Z$) and rainfall rate ($R$) are kept strictly separate.
  - **Status:** `AUTH_REQUIRED` / `LIVE_ACCESS_UNVERIFIED`.
- **ISRO MOSDAC INSAT-3D / INSAT-3DR:**
  - **Adapter Class:** `jalrakshak_ml.weather.adapters.mosdac_insat.MOSDACAdapter`
  - **Architecture:** Supports thermal infrared (TIR1 10.8µm, TIR2 12.0µm), water vapor (WV 6.8µm), cloud-top temperature, and satellite precipitation (HEM, IMSRA).
  - **Status:** `AUTH_REQUIRED` / `LIVE_ACCESS_UNVERIFIED`.

### 2.4 Auth Required
- **IMD DWR Network:** Requires approved institutional Memorandum of Understanding (MoU) with the India Meteorological Department.
- **MOSDAC Open Data:** Requires user registration and API key from https://www.mosdac.gov.in/.
- **NASA Earthdata:** Requires active Earthdata credentials in `~/.netrc` for downloading near-real-time GPM early/late runs.

### 2.5 Unavailable
- Raw radar volume scans (`.iris`, `.h5`) and raw INSAT L1B HDF5 granules do not exist in the repository. The pipeline operates cleanly in degraded mode without crashing or generating fake data.

---

## 3. Degradation Pathways & Hierarchical Fallback Policy

When operational sources experience outages, delays, or authorization blocks, the pipeline executes a deterministic, auditable fallback hierarchy:

```
[Level 1: Ideal Full Operational State]
├── Primary Observation: IMD Doppler Weather Radar (~1 km, 15 min)
├── Atmospheric Context: INSAT-3D/3DR Satellite (4 km, 30 min)
└── Synoptic Guidance: NOAA GFS 0.25° NWP (6h cycle lag)
       │
       ▼ (Radar Unavailable / Auth Blocked)
[Level 2: Satellite-Assisted State]
├── Primary Observation: INSAT QPE (HEM/IMSRA) or GPM Real-time Early Run
├── Cloud / Moisture: INSAT TIR & Water Vapor channels
└── Synoptic Guidance: NOAA GFS 0.25° NWP
       │
       ▼ (Satellite Unavailable)
[Level 3: Archive / Baseline State]
├── Primary Observation: GPM IMERG Final Run (Historical Benchmark Replay Only)
└── Synoptic Guidance: NOAA GFS 0.25° NWP Replay
       │
       ▼ (Extreme Degraded State)
[Level 4: Degraded Single-Source State]
├── Operational Nowcaster: PySTEPS optical flow on latest available observation
└── Missing Channel Mask: missing_channel_mask[c] = True (zeros with valid_mask=False)
```

**Non-Negotiable Fallback Invariants:**
1. Fallback sources are **never relabeled**. GPM is never presented as radar data.
2. Every output carries `fallback_metadata` documenting:
   - `primary_observation_source`
   - `fallback_used` (boolean)
   - `missing_sources` (list of strings)
   - `active_sources` (list of strings)

---

## 4. Multi-Source Tensor Builder Specification

For future deep nowcasting and NWP fusion models, the multi-source tensor builder (`MultiSourceTensorBuilder`) constructs unified tensors:
- **Dimensions:** $(C, H, W) = (11, 256, 256)$
- **Channels:**
  0. `rainfall_gpm` (mm/h)
  1. `radar_reflectivity` (dBZ)
  2. `radar_rainfall` (mm/h)
  3. `satellite_ir` (K)
  4. `satellite_wv` (K)
  5. `gfs_precipitation` (mm/h)
  6. `gfs_u10` (m/s)
  7. `gfs_v10` (m/s)
  8. `gfs_rh2m` (%)
  9. `gfs_t2m` (K)
  10. `gfs_cape` (J/kg)
- **Masking:** Each channel is paired with a boolean `valid_mask` $(C, H, W)$ and an overall `missing_channel_mask` $(C,)$.
- **Training Source Dropout:** Supports random channel dropout during training with configurable probability $p \in [0.1, 0.3]$ to force future neural architectures to remain resilient under missing observation streams.
