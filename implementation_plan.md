# Implementation Plan: Phase 4B — GFS Standalone Benchmark + Multi-Model Fusion Foundation

This plan establishes the research-grade evaluation of standalone GFS weather forecasts on the 51 locked held-out test samples, creates a unified forecast provider contract, implements multi-model fusion baselines (equal, horizon-aware, skill-derived) without data leakage, builds gating infrastructure for future learned fusion, exposes ensemble uncertainty metrics, adds exhaustive tests, and publishes evaluation reports.

## User Review Required

> [!IMPORTANT]
> **Data Integrity and Anti-Leakage Constraints:**
> 1. No test events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`) will ever be used to calibrate fusion weights or train gating models.
> 2. Skill-derived weights will be fitted strictly on train (`mumbai_monsoon_2023_07_18`) and validation (`mumbai_monsoon_2023_07_25`) events.
> 3. Operational nowcaster remains `PySTEPS` unless a fusion method conclusively outperforms it across both MAE and RMSE on the held-out test set without unacceptable degradation of heavy-rain skill.

> [!NOTE]
> Ground-truth GPM IMERG observations for the 2024 held-out events (`2024-08-04` and `2024-09-05`, 24 frames each) will be fetched directly from NASA GES DISC via the existing authenticated GPM adapter, matching the canonical EPSG:32643 256×256 grid.

---

## Proposed Changes

### Component 1: Ground Truth Ingestion for 2024 Benchmark Events
To evaluate standalone GFS and all models on the full 51 held-out test samples:
- Ingest the 24 half-hourly frames (00:00 to 11:30 UTC) for `mumbai_monsoon_2024_08_04` and `mumbai_monsoon_2024_09_05`.
- Save as canonical event stores under `data/processed/training/gpm_imerg_v07_mumbai_monsoon_windows_v1/events/`.
- Update manifest while strictly preserving the `test` split assignment for both 2024 events.

---

### Component 2: Unified Forecast Provider Contract (`src/jalrakshak_ml/fusion/contracts.py`)
Create a backward-compatible, provider-neutral forecast provider interface:
- **`ForecastProvider` Protocol/ABC**:
  - `predict(inputs, lead_times, issue_time, **kwargs) -> ForecastResult`
- **`ForecastResult`** (extending/compatible with `NowcastResult`):
  - `rainfall_mm_h`: `np.ndarray` of shape `[horizon, y, x]`
  - `horizons_min`: list of lead minutes `[30, 60, 90, 120]`
  - `issue_time`: `datetime` (UTC)
  - `valid_mask`: boolean mask `[horizon, y, x]`
  - `provider`: provider identifier string
  - `model_version`: string
  - `data_version`: string
  - `source_metadata`: dict with cycle, latency, native cadence, etc.
  - `uncertainty`: optional dict containing ensemble spread/disagreement/confidence
  - `native_cadence_minutes`: 30 or 60
  - `output_cadence_minutes`: 30
  - `provenance`: full auditable processing chain
- **Provider Adapters**:
  - `PersistenceProvider`
  - `PystepsProvider`
  - `ConvLSTMProvider` (handling V2 checkpoint)
  - `GFSReplayProvider` (loading from `data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1/`)

---

### Component 3: Standalone GFS Benchmark (`src/jalrakshak_ml/gfs_replay/benchmark.py`)
- Evaluate repaired GFS forecasts on the 51 held-out samples:
  - Lead times: +30, +60, +90, +120 min.
  - Metrics: MAE, RMSE, Bias, POD, FAR, CSI, F1, Frequency Bias.
  - Thresholds: 0.1, 1.0, 5.0, 10.0 mm/h (flagging low support if positive cells < min support).
  - Common valid-pixel mask intersection with ground-truth GPM observations.
  - Strict pooled contingency counts.
- Generate:
  - `reports/phase4_gfs_standalone_evaluation.json`
  - `reports/phase4_gfs_standalone_report.md`

---

### Component 4: Multi-Model Fusion Framework (`src/jalrakshak_ml/fusion/`)
Implement in `src/jalrakshak_ml/fusion/`:
- `core.py`:
  - `EqualWeightFusion`: simple arithmetic mean over available providers.
  - `HorizonAwareFixedFusion`: fixed weights per horizon (e.g. Radar-heavy at +30m, NWP-higher at +120m).
  - `SkillDerivedFusion`: weights calibrated using inverse-MAE or optimal convex combination on train/val events only.
  - Missing-provider fallback logic: dynamically re-normalizes weights among valid providers or falls back to operational nowcaster if primary models are unavailable.
- `calibration.py`:
  - Derives optimal weights per horizon strictly from Train (`2023-07-18`) and Validation (`2023-07-25`) replay.
  - Never touches test events.
  - Saves calibrated weights into `configs/fusion/weights_v1.yaml`.
- `uncertainty.py`:
  - Computes provider disagreement (pairwise variance / mean absolute deviation).
  - Ensemble mean and standard deviation (spread).
  - Agreement score and confidence index.
- `gating.py`:
  - Feature builder for gating models:
    - Per-provider: forecast intensity, recent error, valid pixel fraction, disagreement from ensemble mean.
    - Shared: lead time, current rainfall intensity, rain regime, GFS forecast age, availability.
  - Supervised gating baseline interface (LightGBM/Ridge/MLP).
  - Explicit check: if non-test GFS replay is bounded, set `LEARNED_GATE_TRAINED=false` and provide clean infra.

---

### Component 5: Comprehensive Benchmark Evaluation (`scripts/evaluate_phase4b_fusion.py`)
- Evaluates on the 51 locked held-out samples:
  1. `Persistence`
  2. `PySTEPS`
  3. `ConvLSTM V2`
  4. `GFS`
  5. `EqualWeightFusion`
  6. `HorizonAwareFixedFusion`
  7. `SkillDerivedFusion`
  8. `GatingFusion` (if trained)
- Output metrics: overall MAE, RMSE, +30 heavy rain CSI/POD/FAR, +60/+90/+120 stability.
- Determines whether any fusion model passes operational gates over PySTEPS.

---

### Component 6: Tests (`tests/test_fusion.py` & `tests/test_gfs_benchmark.py`)
Automated test suite verifying:
1. `test_no_test_data_calibration`: asserts test split event IDs are rejected during calibration.
2. `test_non_negative_normalized_weights`: weights are $\ge 0$ and sum to $1.0$ per horizon.
3. `test_missing_provider_fallback`: gracefully handles missing NWP or deep model.
4. `test_common_mask_fairness`: verifies identical pixel masks across all evaluated providers.
5. `test_horizon_alignment`: verifies +30, +60, +90, +120 min temporal alignment.
6. `test_gfs_timing_metadata_propagation`: verifies cycle time, availability time, forecast age in outputs.
7. `test_uncertainty_metrics`: verifies ensemble mean, spread, and disagreement calculation.
8. `test_contract_compatibility`: checks conformity with `NowcastResult` schema.
9. `test_event_isolation`: verifies zero data crossover between splits.

---

### Component 7: Documentation & Reports
- `reports/phase4_gfs_standalone_evaluation.json`
- `reports/phase4_gfs_standalone_report.md`
- `reports/phase4_fusion_foundation_report.md` (including machine-readable status block)

---

## Verification Plan

### Automated Tests
Run pytest with all existing and new tests:
```powershell
& "C:\Users\sawan\miniconda3\envs\jalrakshak\python.exe" -m pytest tests/test_gfs_replay.py tests/test_fusion.py tests/test_nowcast_metrics.py tests/test_data_leakage.py -v
```

### End-to-End Benchmark Execution
Run the standalone GFS benchmark and multi-model fusion evaluation scripts:
```powershell
& "C:\Users\sawan\miniconda3\envs\jalrakshak\python.exe" scripts/evaluate_gfs_standalone.py
& "C:\Users\sawan\miniconda3\envs\jalrakshak\python.exe" scripts/evaluate_phase4b_fusion.py
```
Verify generated JSON and Markdown reports.
