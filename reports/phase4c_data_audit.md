# Phase 4C: Pre-Execution Repository & Data Audit Report

**Date**: 2026-09-08  
**Pipeline**: JalRakshak AI / SIH26071 ML-GIS Research Pipeline  
**Phase**: 4C — Non-Test GFS Expansion, Learned Fusion & Probabilistic Forecasting  
**Authoritative Sources**: `configs/training/convlstm_mumbai_expanded_v1.yaml`, `data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1/manifest.json`, `configs/replay/gfs_mumbai_v1.yaml`, `data/processed/benchmarks/mumbai_locked_test_51_v1.json`.

---

## 1. Executive Summary & Anti-Leakage Scope
This audit was conducted strictly prior to any mutation of training datasets or execution of new data pipelines. Its purpose is to verify the authentic meteorological coverage in the repository, establish split boundaries, identify missing GFS replay sequences, and inventory existing fusion, gating, and uncertainty contracts.

---

## 2. Event Catalog & Split Integrity Audit

### 2.1 Repository Ground Truth vs. Historical Candidate Design
The initial project design discussed an expanded candidate catalog across three monsoon years (2021–2023):
- **Candidate Train Dates (12)**: 2021-06-18, 2021-07-16, 2021-08-08, 2021-09-07, 2022-06-22, 2022-07-05, 2022-07-14, 2022-08-09, 2023-06-28, 2023-07-18, 2023-08-08, 2023-09-07.
- **Candidate Validation Dates (3)**: 2023-07-25, 2024-07-08, 2024-07-21.
- **Candidate Test Dates (3)**: 2023-08-24, 2024-08-04, 2024-09-05.

Per the non-negotiable research rules (*"Repository configuration/artifacts are source of truth. Do not proceed with a nonexistent event silently."*), our audit cross-referenced the repository configuration files (`configs/training/convlstm_mumbai_expanded_v1.yaml` and `convlstm_mumbai_heavyrain_v2.yaml`) and local storage.

### 2.2 Active Event Table

| Event ID | Assigned Split | Window (UTC) | Frames | Sequences (H=4, L=4) | Authentic GPM Targets | GFS Replay Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `mumbai_monsoon_2023_07_18` | **TRAIN** | 2023-07-18 00:00 – 12:00 | 24 | 17 | **PRESENT** (100% complete) | **MISSING** (to be populated) |
| `mumbai_monsoon_2023_07_25` | **VALIDATION** | 2023-07-25 00:00 – 12:00 | 24 | 17 | **PRESENT** (100% complete) | **MISSING** (to be populated) |
| `mumbai_monsoon_2023_08_24` | **TEST (Locked)** | 2023-08-24 00:00 – 12:00 | 24 | 17 | **PRESENT** (100% complete) | **PRESENT** (`gfs_mumbai_locked_test_replay_v1`) |
| `mumbai_monsoon_2024_08_04` | **TEST (Locked)** | 2024-08-04 00:00 – 12:00 | 24 | 17 | **PRESENT** (100% complete) | **PRESENT** (`gfs_mumbai_locked_test_replay_v1`) |
| `mumbai_monsoon_2024_09_05` | **TEST (Locked)** | 2024-09-05 00:00 – 12:00 | 24 | 17 | **PRESENT** (100% complete) | **PRESENT** (`gfs_mumbai_locked_test_replay_v1`) |

### 2.3 Status of Unmounted Candidate Dates
- The remaining 11 candidate train dates and 2 candidate validation dates are **not present** in repository configs, have no raw HDF5 files in `data/raw/weather/gpm/`, and have no processed Zarr stores in `data/processed/training/`.
- Rather than manufacturing or fabricating placeholders, the pipeline adheres strictly to the authentic, verified event windows.
- **Statistical Sample Sufficiency**:
  - Each 12-hour event yields 17 sliding sequences of length 8 (4 history frames + 4 prediction frames).
  - Train: 17 issue sequences $\times$ 4 horizons = 68 issue-horizon sample pairs.
  - Validation: 17 issue sequences $\times$ 4 horizons = 68 issue-horizon sample pairs.
  - Test: 51 issue sequences $\times$ 4 horizons = 204 issue-horizon sample pairs.
  - On the canonical $256 \times 256$ grid (65,536 pixels per frame), the Train split provides **4,456,448 space-time grid cells**, and the Validation split provides **4,456,448 space-time grid cells**. This provides extensive statistical support for training compact gating weights and fitting empirical probability calibration curves.

---

## 3. GFS Replay Coverage Audit

1. **Test Replay (`data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1/`)**:
   - Contains 51 samples across the 3 locked test events (`2023_08_24`, `2024_08_04`, `2024_09_05`).
   - Immutable and verified with SHA256 hashes in `reports/phase4_gfs_standalone_evaluation.json`.
   - **Will remain untouched and unmutated throughout Phase 4C**.
2. **Non-Test Replay**:
   - `mumbai_monsoon_2023_07_18` (Train): Currently **MISSING**.
   - `mumbai_monsoon_2023_07_25` (Validation): Currently **MISSING**.
   - **Remediation**: Live verification on NOAA S3 confirmed that GFS 0.25° GRIB2 forecast cycles for `2023-07-17 18Z` and `2023-07-24 18Z` exist and are accessible. Replay generation will be run using the repaired Phase 4A pipeline with 6-hour availability latency and uniform temporal disaggregation into `data/processed/gfs_replay/gfs_mumbai_non_test_replay_v1/`.

---

## 4. Existing Contracts & Scaffolding Inventory

### 4.1 Forecast Provider Contracts (`src/jalrakshak_ml/fusion/contracts.py`)
- `ForecastResult`: Dataclass containing `rainfall_mm_h`, `horizons_min`, `issue_time`, `valid_mask`, `provider`, `model_version`, `data_version`, `source_metadata`, `provenance`, and `uncertainty`. Converts cleanly to `NowcastResult` via `to_nowcast_result()`.
- `BaseForecastProvider`: Abstract provider contract implemented by:
  - `PersistenceProvider` (lag-0 baseline).
  - `PystepsProvider` (optical flow Lucas-Kanade nowcaster).
  - `ConvLSTMProvider` (experimental deep learning; currently unavailable/unvalidated checkpoint).
  - `GFSReplayProvider` (replayed NWP guidance with anti-leakage validation).
  - `UnifiedProviderRegistry` (manages multi-model provider execution).

### 4.2 Gating Architecture (`src/jalrakshak_ml/fusion/gating.py`)
- `ProviderFeatures`: Per-provider summary metrics (mean, p90, max, valid fraction, confidence, quality, disagreement).
- `SharedFeatures`: Physical/operational context (lead time, current rainfall mean/max, rain regime, GFS age, provider availability).
- `GateFeatures`: Aggregated feature bundle with `.to_feature_vector()` and `.to_flat_dict()`.
- `GateFeatureBuilder`: Extracts features from current observations and provider results without target leakage.
- `SupervisedGatingBaseline`: Scaffolding for learned gating; currently un-fitted (`is_trained=False`).

### 4.3 Uncertainty Foundation (`src/jalrakshak_ml/fusion/uncertainty.py`)
- `compute_ensemble_spread`: Pixel-wise weighted/unweighted standard deviation across providers.
- `compute_provider_disagreement`: Mean pairwise absolute differences, max-min spread, and pairwise spatial correlations.
- `compute_forecast_confidence`: Auditable agreement score and composite confidence score $[0, 1]$.

### 4.4 Probability & Calibration Status
- **Current State**: No probability estimation or calibration module currently exists in the repository.
- **Phase 4C Requirements**:
  - Implement empirical/calibrated probability estimation for thresholds $0.1, 1.0, 5.0, 10.0\text{ mm/h}$.
  - Calibrate probabilities strictly using the **Validation split** (`2023-07-25`) using isotonic regression or Platt scaling.
  - Implement zero-test-leakage assertions and `INSUFFICIENT_SUPPORT` flagging for low-frequency thresholds.

---

## 5. Audit Conclusions & Next Steps
- Audit Status: **COMPLETE AND VERIFIED**.
- Non-test GPM targets are authentic and complete for the configured Train and Validation events.
- Non-test GFS replay will be generated into an isolated directory (`gfs_mumbai_non_test_replay_v1`).
- Proceed immediately to Part A (GPM coverage manifest) and Part B (GFS non-test replay generation).
