# Phase-2 Validation Gate (Step 18.5)

This plan details the strict validation steps required before proceeding to Phase 3 (Deep Learning / ConvLSTM). We will prove that the pipeline and baselines operate correctly on a genuine historical Mumbai rainfall event using actual data from NASA GPM IMERG.

## User Review Required
> [!IMPORTANT]
> The historical event selected is **July 25-26, 2023**, a period of heavy rainfall in Mumbai. We will use the native ~30-minute temporal resolution of GPM IMERG without artificially upsampling to 10 minutes.
> 
> As you warned, PySTEPS typically expects high-frequency radar data (5-10 mins). If PySTEPS struggles with the 30-minute GPM data (e.g., optical flow vectors become unstable due to the large time gap between frames), we will report this honestly rather than interpolating. 

## Proposed Changes

### 1. Data Ingestion & Data Audit
- Trigger GPM IMERG and GFS data ingestion for the July 2023 Mumbai event using the configured Earthdata credentials.
- Ensure the data flows correctly through the QC frame into `weather.zarr`.
- Create a comprehensive audit script `scripts/audit_phase2_data.py`.
- **Outputs**: `reports/phase2_data_audit.json` containing metadata, missing percentages, min/max values, and a boolean flag proving the data is `REAL`.

### 2. Evaluation Metrics & Data Leakage Check
- **Metrics Extension**: Update `src/jalrakshak_ml/evaluation/metrics.py` to add `F1 Score`. Add stub interfaces for `Brier Score` and Reliability calibration for future probabilistic forecasts.
- **Leakage Test**: Add an automated test `tests/test_data_leakage.py` that verifies the `NowcastEvaluator` strictly splits past/future and feeds only `T <= 0` to the models.
- **Output Contract**: Assert that `PersistenceNowcast` and `PystepsNowcast` both adhere to the `(lead_times, height, width)` canonical output shape.

### 3. Baseline Replay & Metrics Generation
- Extract the chronological sequence (e.g., T-90 to T+120) from the downloaded `weather.zarr`.
- Run `PersistenceNowcast` and `PystepsNowcast` natively on the 30-minute GPM intervals.
- Save the metrics comparison table.

### 4. Visualization & Reporting
- Generate `notebooks/07_real_event_baseline_replay.ipynb` to visualize observed rainfall vs. Persistence vs. PySTEPS, alongside error maps.
- **Outputs**: `reports/phase2_baseline_report.md` summarizing the event details, source resolutions, limitations, baseline metric comparisons, and the final readiness verdict (`PHASE_3_READY=true|false`).

## Verification Plan

### Automated Tests
- Run `pytest tests/test_data_leakage.py`
- Run `pytest tests/test_nowcast_metrics.py`

### Manual Verification
- The generated `reports/phase2_baseline_report.md` will contain the final verdict on whether the real data pipelines and baseline architectures are solid enough to warrant advancing to the ConvLSTM deep learning phase (Phase 3).
