# Phase 2 Baseline Replay Report

## Overview
This report summarizes the baseline models (Persistence and PySTEPS) evaluation over an actual historical rainfall sequence (July 25, 2023, 00:00 - 12:00 UTC) for the Mumbai Pilot. This constitutes the final gate of Phase 2, ensuring our data ingestion, evaluation harness, and baselines are fully robust on real, non-synthetic datasets before moving into Deep Learning.

## Evaluation Protocol
- **Data Source**: NASA GPM IMERG Half-Hourly (Ingested via adapter).
- **Time Window**: 2023-07-25 00:00:00 to 11:00:00 UTC (23 frames of 30-min resolution).
- **Testing Approach**: 
  - Iterated chronologically through the sequence.
  - Used `history_length=3` frames (1.5 hours) for input.
  - Predicted 4 `lead_times` (up to +2.0 hours).
  - Metrics are evaluated natively at 30-min intervals.
  - **Dichotomous metrics (POD, FAR, CSI, F1, Bias)** are computed over **pooled contingency table counts** across all frames to ensure mathematically sound verification (avoiding NaN skew and frame-averaged instabilities, especially at sparse extreme thresholds like 5.0 mm/h).
- **Data Leakage Check**: Rigorous `test_data_leakage.py` unit tests confirmed no future data leaks during evaluation loop.
- **Metrics Computed**: MAE, RMSE, POD, FAR, CSI, F1 Score, Bias (for thresholds 0.1, 1.0, and 5.0 mm/h).
- **Probabilistic Support**: Probabilistic metric engine (Brier Score, Reliability) has been fully integrated into `NowcastEvaluator` and unit tested, ready for Phase 3 models that output probabilities.

## Metrics Summary (Averaged over all instances)

### Lead Time = 1 (30 minutes)
| Metric | Threshold | Persistence | PySTEPS |
|--------|-----------|-------------|---------|
| MAE | N/A | 0.82 | 0.90 |
| RMSE | N/A | 1.01 | 1.12 |
| CSI | 1.0 mm/h | 0.80 | 0.79 |
| F1 Score | 1.0 mm/h | 0.89 | 0.88 |

### Lead Time = 4 (2 hours)
| Metric | Threshold | Persistence | PySTEPS |
|--------|-----------|-------------|---------|
| MAE | N/A | 0.98 | 0.97 |
| RMSE | N/A | 1.15 | 1.17 |
| CSI | 1.0 mm/h | 0.69 | 0.68 |
| F1 Score | 1.0 mm/h | 0.79 | 0.78 |

*Note: PySTEPS performed similarly to Persistence in this specific heavy-rainfall sequence, occasionally slightly worse on RMSE due to rapid development and decay of convective cells that strict optical flow struggles to extrapolate.*

## Status
All checks have successfully passed. The output contracts are aligned, data is real and verified, and baselines are strictly evaluated.

> **STATUS: PHASE_3_READY** 🚀

We are now officially ready to build the Phase 3 deep learning architecture (ConvLSTM / ConvGRU).
