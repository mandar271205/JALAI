# Phase 4D: Repository & Meteorological Source Capability Audit

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4D — Part 0 Source Audit  
**Author:** Antigravity AI  

---

## 1. Executive Summary

This audit establishes the empirical capability, access boundaries, authentication requirements, and latency realities for all meteorological and contextual data sources evaluated in the JalRakshak AI pipeline.

In accordance with strict scientific non-negotiable rules:
- No meteorological data is fabricated or synthesized.
- No synthetic radar reflectivity or rainfall grids are generated.
- No low-resolution data (e.g. 0.1° GPM or 0.25° GFS) is ever described as neighborhood-scale (160 m) weather.
- Quality scores $[0, 1]$ are strictly decoupled from model forecast confidence $[0, 1]$.
- Data availability is verified as-of simulated issue times to prevent future temporal leakage.

---

## 2. Source Classification & Capability Matrix

| Source / Product | Provider | Native Spatial Res | Native Cadence | Expected Operational Latency | Local Archive Present | Public API / Remote Access | Classification Status | Operational Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GPM IMERG V07 (Final Run)** | NASA / JAXA | 0.1° (~10 km) | 30 min | ~3.5 months | **Yes** (120 frames across 5 events in repo) | Earthdata (requires credentials) | `READY` (Historical) / `ARCHIVE_ONLY` / `GROUND_TRUTH_ONLY` | Benchmark Evaluation / Historical Training Ground Truth |
| **GPM IMERG (Early / Late Run)** | NASA / JAXA | 0.1° (~10 km) | 30 min | 4h (Early) / 14h (Late) | No | Earthdata (unconfigured) | `ADAPTER_ONLY` / `AUTH_REQUIRED` | Potential Near-Realtime Satellite Observation |
| **NOAA GFS (0.25° Global)** | NOAA NCEP | 0.25° (~28 km) | 60 min (0–120h) | 5.5 to 6.0 hours | **Yes** (485MB f000 + indexed replay cache) | AWS S3 Open Data (`noaa-gfs-bdp-pds`) — No Auth | `READY` / `REALTIME_ELIGIBLE` | Synoptic NWP Guidance (>6h cycle lag) |
| **IMD Doppler Radar (Colaba/Veravali)** | IMD | ~1 km (polar converted) | 10–15 min | 15–30 min | **No** | IMD restricted network (requires institutional MoU) | `ADAPTER_ONLY` / `AUTH_REQUIRED` / `LIVE_ACCESS_UNVERIFIED` | Primary Nowcasting Observation (Interface-Ready) |
| **MOSDAC INSAT-3D/3DR (IR/WV/QPE)** | ISRO MOSDAC | 4 km (IR/WV) / 1 km (VIS) | 15–30 min | 30–60 min | **No** | MOSDAC Portal (requires registered token) | `ADAPTER_ONLY` / `AUTH_REQUIRED` / `LIVE_ACCESS_UNVERIFIED` | Regional Cloud/Moisture/QPE Observation (Interface-Ready) |
| **IMD AWS Surface Gauges** | IMD | Point observations | 15–60 min | 1–3 hours | **No** | IMD Pune portal (restricted) | `ADAPTER_ONLY` / `AUTH_REQUIRED` | Ground Validation & Gauge Correction |
| **Copernicus DEM (GLO-30)** | ESA / Copernicus | 30 m | Static | Zero (precomputed) | **Yes** (`data/processed/static/elevation.npy`) | Pre-ingested | `READY` | Static Topographic Context |
| **OpenStreetMap Infrastructure** | OSM Contributors | Vector geometry | Static / periodic | Zero (precomputed) | **Yes** (`data/processed/static/`) | Pre-ingested | `READY` | Static Vulnerability & Asset Context |

---

## 3. In-Depth Source Audit Findings

### 3.1 NASA GPM IMERG V07
- **Product Identified:** GPM IMERG Final Precipitation L3 Half Hourly 0.1° x 0.1° (`3B-HHR.MS.MRG.3IMERG`).
- **Data Availability in Repo:** 120 processed frames across 5 monsoon episodes (Train: `2023_07_18`, Val: `2023_07_25`, Test: `2023_08_24`, `2024_08_04`, `2024_09_05`).
- **Operational Reality:** The "Final" product incorporates monthly climatological gauge adjustments and requires multi-month latency (~3.5 months). It is strictly **`GROUND_TRUTH_ONLY`** and cannot be used in real-time operational nowcasting.
- **Physical Interpretation:** Pixel size is ~11 km over Mumbai. Reprojection to 160 m or 256x256 grid is spatial resampling, **not physical downscaling**.

### 3.2 NOAA GFS 0.25° NWP
- **Product Identified:** Global Forecast System quarter-degree pgrb2 (`atmos/gfs.t{HH}z.pgrb2.0p25.f{lead:03d}`).
- **Access Protocol:** HTTP byte-range requests directly from AWS Open Data (`https://noaa-gfs-bdp-pds.s3.amazonaws.com/`). No API keys or authentication required.
- **Decoded Variables:**
  - `PRATE:surface:0-X hour ave fcst` (`shortName="prate"`, `typeOfLevel="surface"`, `level=0`, `stepType="avg"`, units=`kg m**-2 s**-1`).
  - `APCP:surface:0-X hour acc fcst` (`shortName="tp"`, `typeOfLevel="surface"`, `level=0`, `stepType="accum"`, units=`kg m**-2`).
  - Additional rich variables verified present in GFS index: `10u`, `10v`, `2t`, `2r`, `sp`, `cape`, `pwat`.
- **Latency & Anti-Leakage:** Operational GFS cycles are published with a 5.5 to 6.0-hour delay from cycle initialization. The pipeline strictly enforces `availability_time = cycle_time + 6h <= issue_time`.

### 3.3 IMD Doppler Weather Radar (Mumbai)
- **Stations:** Mumbai Colaba (`VABB`, $18.898^\circ\text{N}, 72.810^\circ\text{E}$, C-band) and Veravali backup ($19.133^\circ\text{N}, 72.867^\circ\text{E}$, S-band).
- **Access Status:** IMD Doppler radar volume scans (IRIS / HDF5 formats) are restricted to government and research partners with formal MoUs. No active API key, FTP endpoint, or raw volume scans exist in the local workspace.
- **Adapter State:** Interface and parsing scaffold implemented. Health checks return `AUTH_REQUIRED` / `LIVE_ACCESS_UNVERIFIED`. No fake radar grids are generated.
- **Z-R Formulation:** Scaffolds support standard Marshall-Palmer ($Z = 200 R^{1.6}$) and tropical maritime ($Z = 250 R^{1.2}$) conversions, but reflectivity ($Z$) and precipitation rate ($R$) are kept strictly as distinct fields.

### 3.4 MOSDAC INSAT-3D / INSAT-3DR
- **Instruments:** Imager (6 channels) and Sounder (19 channels).
- **Products:** Cloud-top temperature, brightness temperatures (TIR1 10.8µm, TIR2 12.0µm, WV 6.8µm), quantitative precipitation estimates (HEM, IMSRA).
- **Access Status:** Data access requires institutional authorization at `https://www.mosdac.gov.in/`. No user credentials or tokens exist locally.
- **Adapter State:** Complete adapter scaffold implemented. Status returns `AUTH_REQUIRED`. Zero synthetic satellite data emitted.

---

## 4. Anti-Leakage & Governance Invariants

1. **Simulated Issue-Time Invariant:**
   $$\forall \text{ source } s, \quad \text{availability\_time}(s) \le \text{issue\_time}$$
   Any record violating this condition is rejected with an explicit `ValueError("Anti-leakage violation")`.

2. **Ground Truth vs. Real-Time Separation:**
   - Sources tagged `GROUND_TRUTH_ONLY` (e.g. GPM V07 Final) are prohibited from serving as operational nowcaster inputs in real-time mode.
   - Sources tagged `REALTIME_ELIGIBLE` (e.g. GFS with 6h lag) may serve as operational inputs.

3. **Decoupling of Quality Score and Forecast Confidence:**
   - $\text{quality\_score} \in [0, 1]$ represents the physical validity, completeness, and freshness of the meteorological input data.
   - $\text{forecast\_confidence} \in [0, 1]$ represents the predictive certainty of the nowcaster or NWP forecast.
   - They are never merged into a single metric.
