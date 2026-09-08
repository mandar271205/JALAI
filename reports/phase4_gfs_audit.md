# Phase 4 GFS/NWP audit

Audit date: 2026-09-08. Scope: verification only. Operational PySTEPS and experimental ConvLSTM V2 are treated as locked; no training or fusion implementation was performed.

## Verdict

The repository has a download/parser scaffold and a reusable target grid, but **no scientifically usable GFS replay pipeline**. Variable selection, precipitation units, spatial referencing, time alignment, and forecast availability provenance need repair before fusion.

## Existing implementation and exact variables

Inspected `adapters/gfs.py`, `scripts/ingest_gfs.py`, `preprocessing/grid.py`, `pipelines/cube_pipeline.py`, `qc/frame_qc.py`, both Python WeatherFrame definitions, JSON/OpenAPI contracts, source/pilot/training configs, baseline/held-out evaluation code, tests, local GRIB and Zarr metadata. Python paths below are relative to `src/jalrakshak_ml/`.

Actual source: public NOAA AWS bucket `noaa-gfs-bdp-pds`, through HTTPS:
`https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF`.
The `_NOMADS_BASE` name and NOMADS docstrings are misleading: the code downloads full AWS GRIB2 objects with `urllib.request.urlretrieve`, using an existence-only local cache. No range/subset download, integrity validation of cached source files, or NetCDF path is implemented. [NOAA AWS dataset registry](https://registry.opendata.aws/noaa-gfs-bdp-pds/).

| Intended source field | Configured ecCodes short name / level | Native units | Current handling |
|---|---|---|---|
| APCP total precipitation | `tp`, surface | kg/m², numerically mm water equivalent | Declares `mm`; no rate conversion |
| TMP | `2t`, 2 m above ground | K | Declares K |
| RH | `2r`, 2 m above ground | % | Declares % |
| UGRD / VGRD | `10u` / `10v`, 10 m above ground | m/s | Declares m/s |
| PRATE precipitation rate | `prate`, surface | kg/m²/s | Present in source, not selected by adapter config |

Precipitation fields can have instantaneous, average, or accumulation step semantics. Match the intended GRIB message and its time interval, not merely its label. [NCEP forecast inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml).

**Parser defect:** `xarray.open_dataset(engine='cfgrib', indexpath='')` filters only `typeOfLevel`. Configured `shortName` and `level` are ignored; the first 2-D variable is returned under each requested name. Mixed levels/steps can also cause cfgrib failures, which are swallowed. A controlled in-memory dataset containing pressure first and precipitation second returned **100000 as precipitation**, confirming misselection. No production files were changed by this check.

Local raw inventory: one 485,123,757-byte `20230725_00Z_gfs.t00z.pgrb2.0p25.f000`. An ecCodes header scan found visibility (`vis`, m) as its first surface message, instantaneous PRATE at step zero, and **no `tp` message**. Thus f000 cannot supply the intended positive-duration APCP interval. This supports a variable-misselection explanation for the cube; exact old processing provenance is unavailable.

## Cadence, units, and requested horizons

GFS cycles are 00/06/12/18 UTC. The selected 0.25-degree product provides hourly near-term forecasts through +120 hours; longer-range products are coarser. It has **no native 30-minute forecasts**. [NCEP cadence documentation](https://www.nco.ncep.noaa.gov/pmb/products/gfs/nomads/).

`ingest_gfs.py` fetches only f000 from a fixed 00Z cycle, ignores `end_date`, repeats that array to the length of the existing GPM time axis, and appends it without preserving GFS valid times or manifests. This is neither hourly ingestion nor interpolation. +60/+120 can coincide with native forecast boundaries; +30/+90 cannot when the issue is on an hourly boundary. For half-hour issue times, the alignment shifts. None of these four outputs is currently implemented correctly.

APCP conversion is absent: metadata remains `mm` and the values are written into `rainfall_gfs`. Do not expose these as API rainfall rates. Derive interval amount from `startStep`, `endStep`, `stepType`, and source units; divide by interval duration in hours to get **mm/h**. Difference cumulative fields only when they share the same cycle and accumulation origin; handle reset boundaries explicitly. PRATE in kg/m²/s converts to mm/h by multiplying by 3600, while retaining whether it is instantaneous or interval averaged. A zero-duration analysis field must never be divided by zero or treated as an hourly accumulation.

Scientifically defensible next temporal strategy: use a single eligible forecast vintage, reconstruct nonoverlapping precipitation intervals, and conservatively allocate each interval amount to the requested half-hour windows by temporal overlap. A one-hour total A yields a constant rate A mm/h for each half hour (amount A/2 in each); this is an explicitly assumed within-hour distribution, not new GFS information. Preserve native cadence, interval bounds, cycle, forecast age, and disaggregation method. Do not linearly interpolate raw cumulative totals across resets or cycles. For instantaneous ancillary fields, same-vintage interpolation is possible only with explicit labeling. Never use future observations or later-issued cycles to fill a gap.

## Canonical grid and stored data

Native GRIB grid: 1440×721, 0.25° spacing, approximately 28 km north–south and 26 km east–west near Mumbai. Resampling cannot create neighborhood-scale detail.

Existing pilot: bbox `[72.75,18.85,73.05,19.30]`, 256×256, internal **EPSG:32643**, API **EPSG:4326**. Computed pixel sizes are approximately **125.68×196.08 m** (mean 160.88 m); existing `~120m` strings are inaccurate. The pilot's generic temporal setting is 10 minutes, separate from the locked 30-minute forecast contract; it must not be used to imply native GFS cadence.

`reproject_array` uses Rasterio bilinear resampling from EPSG:4326. However, GFS cropping selects grid centers and discards coordinates, then passes the requested bbox as raster bounds. For this bbox, selected centers are only longitudes 72.75/73.00 and latitudes 19.25/19.00. Their actual cell edges differ from the bbox. The code stretches/mislocates the source pixels and has no surrounding interpolation halo. Reuse the target grid, but derive the source affine from actual coordinates/cell edges and verify orientation, longitude wrapping, nodata, and spatial coverage first. Grid shape alone does not certify alignment.

Read-only Zarr check: `rainfall_gfs` is `(4,256,256)`, all finite values equal **500**; `time` and GPM have 23 frames (2023-07-25 00:00–11:00 UTC); temperature/humidity/winds have zero frames. The precipitation QC clips values to [0,500], which can hide a wrongly selected field. `clean_weather_zarr.py` cleans only GPM/time. The four GFS frames lack a reliable independent time/units mapping and are unusable for fusion. Phase-2's existence/missingness audit does not establish GFS physical correctness.

## Historical availability and replay feasibility

Read-only HTTP HEAD plus small `.idx` requests on 2026-09-08 verified f001 GRIB objects for all three dates (00Z). All returned HTTP 200. No historical GRIB was downloaded.

| Held-out event | f001 object size | Index evidence | Current replay readiness |
|---|---:|---|---|
| `mumbai_monsoon_2023_08_24` | 535,590,795 bytes | Instant PRATE; 0–1 h mean PRATE and accumulated APCP | No; archive source exists |
| `mumbai_monsoon_2024_08_04` | 538,990,671 bytes | Same field/interval categories | No; archive source exists |
| `mumbai_monsoon_2024_09_05` | 515,935,222 bytes | Same field/interval categories | No; archive source exists |

Reproducible evidence URLs: [2023-08-24 index](https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20230824/00/atmos/gfs.t00z.pgrb2.0p25.f001.idx), [2024-08-04 index](https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20240804/00/atmos/gfs.t00z.pgrb2.0p25.f001.idx), [2024-09-05 index](https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20240905/00/atmos/gfs.t00z.pgrb2.0p25.f001.idx).

Additional HEAD/index checks also returned HTTP 200 for f002, f003, f006, and f007 on all three dates (15 GRIB objects checked in total). The first three contain 0–2, 0–3, and 0–6-hour APCP respectively. At f007 the two APCP entries separate into **6–7-hour** and **0–7-hour** accumulations. This directly confirms the need to distinguish interval and cycle-total products; hourly file spacing does not imply an hourly accumulation field. Early indexes contain two APCP entries with the same textual interval, so GRIB statistical metadata must disambiguate them. Archive spot checks establish source feasibility, not full event coverage or operational availability at issue time. Check preceding-day cycles and every required lead after fixing the exact event windows. The local snapshot contains only the older three-event 72-frame manifest, including 2023-08-24 00:00–12:00 UTC; the two requested 2024 event manifests are absent. Accept the user's completed benchmark as locked, but obtain its exact manifests/issue schedule for replay rather than inventing dates' start/end windows.

## Temporal leakage and contracts

**No-leakage cannot be certified for GFS replay.** There is no as-of cycle selector, per-file release/availability time, forecast reference-time coordinate, accumulation interval contract, or GFS-specific leakage test. Adapter `valid_time` is reconstructed from caller arguments without validation against GRIB timestamps. Processing wall-clock time is not historical publication time. The two WeatherFrame schemas differ; the adapter's schema lacks the JSON contract's explicit CRS/bbox/object URI, and neither requires forecast-cycle/availability/interval fields. QC duplicate keys omit variable and cycle, and future-time QC compares against today's clock rather than simulated issue time.

Existing baseline and held-out evaluators use GPM histories and do not consume GFS, so the inspected paths show no GFS leakage into those results. The existing leakage test manually slices a dummy history; it does not exercise GFS selection. Relevant existing tests passed: `pytest -q tests/test_data_leakage.py tests/test_config.py tests/test_qc.py` → **11 passed**. These are regression checks, not proof that NWP replay is leakage-safe.

Required replay invariant: every source forecast used must have been available by the simulated issue time; cycle initialization alone is insufficient. Use archived availability evidence or a documented conservative latency policy, select one eligible cycle per issue, and fetch enough leads through issue+120 minutes. Forecast valid times after issue are legitimate; later cycle analyses/forecasts are not. Keep all three named events held out from any future calibration or fusion-weight selection.

## Recommended next implementation step and blockers

Implement and test a **standalone GFS replay preparation pipeline before fusion**: exact GRIB selectors and interval metadata; accumulation/rate conversion; coordinate-correct reprojection; versioned cycle/lead/availability-aware storage; conservative half-hour interval mapping; and as-of replay tests. Add known-value fixtures for wrong-variable rejection, accumulation resets, mass conservation, grid alignment, and unavailable-cycle rejection. Fail explicitly on missing fields rather than writing placeholder rainfall.

Blockers: corrupt/misaligned existing GFS cube, missing conversion and provenance, absent GFS-specific tests, unverified historical publication latency, and missing local 2024 event windows. Source archive access is available for the checked files. No changes to models, checkpoints, baselines, adapters, or fusion code were made; this report is the only authored artifact.

```text
PHASE_4_GFS_AUDIT_COMPLETE=true
GFS_HISTORICAL_REPLAY_READY=false
GFS_CANONICAL_GRID_READY=false
GFS_30MIN_NATIVE=false
FUSION_IMPLEMENTATION_STARTED=false
```
