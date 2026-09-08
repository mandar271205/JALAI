# Task: Phase 4C — Non-Test GFS Expansion, Learned Fusion & Probabilistic Forecasting

## Current Phase
Phase 4C (JalRakshak AI / SIH26071 ML-GIS research pipeline)

## Status
In Planning Mode. Conducting Part 0 data audit and designing execution architecture.

## Phase 4C Breakdown
- [ ] Part 0: Inspect repository catalog and write `reports/phase4c_data_audit.md` <!-- id: 0 -->
- [ ] Part A: Verify authentic non-test GPM targets & generate coverage manifest <!-- id: 1 -->
- [ ] Part B: Expand non-test GFS historical replay & create manifest <!-- id: 2 -->
- [ ] Part C: Create dedicated multi-provider fusion dataset (Train/Val) <!-- id: 3 -->
- [ ] Part D: Train supervised learned gating model (Compact PyTorch MLP) <!-- id: 4 -->
- [ ] Part E: Evaluate & validate learned gate on Validation split before touching Test <!-- id: 5 -->
- [ ] Part F: Implement Probabilistic Forecasting V1 (exceedance probabilities, spread, confidence) <!-- id: 6 -->
- [ ] Part G: Calibrate probabilities strictly on Validation split <!-- id: 7 -->
- [ ] Part H: Compute probabilistic metrics (Brier score, reliability, ROC/PR-AUC) <!-- id: 8 -->
- [ ] Part I: Final untouched held-out evaluation on 51 test samples <!-- id: 9 -->
- [ ] Part J: Apply model selection policy (MAE/RMSE, operational decision) <!-- id: 10 -->
- [ ] Part K: Backwards-compatible contract extension in `contracts.py` <!-- id: 11 -->
- [ ] Part L: Verify graceful degradation & missing-provider policies <!-- id: 12 -->
- [ ] Part M: Generate all research reports and configuration artifacts <!-- id: 13 -->
- [ ] Part N: Create reproducible plotting script for visual artifacts <!-- id: 14 -->
- [ ] Part O: Add comprehensive tests in `tests/test_fusion_phase4c.py` and run full suite <!-- id: 15 -->
- [ ] Part P: Publish final research report and status block <!-- id: 16 -->
