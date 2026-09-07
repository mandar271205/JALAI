# Phase-2 Validation Gate Tasks

- [x] 1. Data Ingestion & Data Audit
  - [x] Trigger GPM IMERG and GFS data ingestion for July 25-26, 2023.
  - [x] Write `scripts/audit_phase2_data.py`.
  - [x] Generate `reports/phase2_data_audit.json`.
- [x] 2. Evaluation Metrics & Data Leakage Check
  - [x] Add `F1 Score`, `Brier Score` (stub), `reliability` (stub) to `metrics.py`.
  - [x] Add `tests/test_data_leakage.py`.
  - [x] Ensure Output Contract is strictly identical.
- [x] 3. Baseline Replay & Metrics Generation
  - [x] Create `phase2_data_audit.json` to verify source datasets
- [x] Clean duplicates from `weather.zarr` via script
- [x] Enforce evaluation metrics and data leakage strict checks
- [x] Create historical replay notebook (`create_nb_07.py`) with animations and visual error maps
- [x] Run `run_baseline_eval.py` over clean history
- [x] Final hand-off summary `phase2_handoff_summary.md` and `PHASE_3_READY` flag.
  - [x] (If ready) Prepare Colab folder structure.
