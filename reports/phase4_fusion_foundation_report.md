# Phase 4B: Multi-Model Forecast Fusion Benchmark Report

## 1. Executive Summary & Verification Scope
- **Benchmark**: `mumbai_locked_test_51_v1` across 51 held-out test sequences from 3 independent monsoon events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`).
- **Common Valid Cells Evaluated**: 10,312,902 space-time cells under strict pairwise mask intersection.
- **Calibrated Splits**: Strictly Train (`mumbai_monsoon_2023_07_18`) and Validation (`mumbai_monsoon_2023_07_25`). Zero test event data was touched during weight calibration.
- **Primary Selection Criteria**: Overall MAE and overall RMSE across all lead times.

## 2. Benchmark Comparison (Overall Performance)

| Model / Pipeline | Overall MAE (mm/h) | Overall RMSE (mm/h) | Mean Bias (mm/h) | CSI (1.0 mm/h) | CSI (5.0 mm/h) | Operational Role |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `persistence` | **0.6723** | **1.0844** | -0.0020 | 0.5545 | 0.2380 | Baseline |
| `pysteps` | **0.6465** | **1.0355** | -0.0692 | 0.5367 | 0.2989 | Operational Baseline |
| `gfs` | **1.0869** | **1.6933** | 0.5111 | 0.5089 | 0.0232 | NWP Guidance |
| `fusion_equal` | **0.7223** | **1.0523** | 0.2210 | 0.5664 | 0.0991 | Fusion Candidate |
| `fusion_horizon_fixed` | **0.7091** | **1.0493** | 0.2230 | 0.5665 | 0.1053 | Fusion Candidate |
| `fusion_skill_derived` | **0.7015** | **1.0424** | 0.2148 | 0.5683 | 0.1142 | Fusion Candidate |

## 3. Lead-Time Progression (+30m, +60m, +90m, +120m)

### Mean Absolute Error (MAE in mm/h) by Horizon
| Model | +30 min | +60 min | +90 min | +120 min |
|:---|:---:|:---:|:---:|:---:|
| `persistence` | 0.4334 | 0.6434 | 0.7633 | 0.9093 |
| `pysteps` | 0.4080 | 0.5988 | 0.7568 | 0.8842 |
| `gfs` | 1.1921 | 1.1096 | 1.0323 | 0.9867 |
| `fusion_equal` | 0.6591 | 0.6852 | 0.7466 | 0.8185 |
| `fusion_horizon_fixed` | 0.4977 | 0.6852 | 0.8088 | 0.8967 |
| `fusion_skill_derived` | 0.4790 | 0.6605 | 0.8185 | 0.9045 |

### Root Mean Squared Error (RMSE in mm/h) by Horizon
| Model | +30 min | +60 min | +90 min | +120 min |
|:---|:---:|:---:|:---:|:---:|
| `persistence` | 0.7495 | 1.0358 | 1.1719 | 1.3626 |
| `pysteps` | 0.6885 | 0.9503 | 1.1505 | 1.3236 |
| `gfs` | 1.8873 | 1.7823 | 1.5920 | 1.4118 |
| `fusion_equal` | 0.9998 | 1.0110 | 1.0673 | 1.1428 |
| `fusion_horizon_fixed` | 0.7382 | 1.0110 | 1.1797 | 1.2579 |
| `fusion_skill_derived` | 0.7125 | 0.9691 | 1.1974 | 1.2713 |

### Critical Success Index (CSI @ 1.0 mm/h) by Horizon
| Model | +30 min | +60 min | +90 min | +120 min |
|:---|:---:|:---:|:---:|:---:|
| `persistence` | 0.7260 | 0.6084 | 0.4861 | 0.3869 |
| `pysteps` | 0.6999 | 0.5957 | 0.4619 | 0.3774 |
| `gfs` | 0.5447 | 0.5407 | 0.5091 | 0.4251 |
| `fusion_equal` | 0.6464 | 0.6215 | 0.5332 | 0.4423 |
| `fusion_horizon_fixed` | 0.6876 | 0.6215 | 0.5168 | 0.4174 |
| `fusion_skill_derived` | 0.6941 | 0.6268 | 0.5143 | 0.4167 |

## 4. Scientific Findings & Operational Decision
1. **Operational Nowcaster Retention**: PySTEPS overall MAE is `0.6465` mm/h and RMSE is `1.0355` mm/h.
2. **Operational Safeguard Enforced**: No fusion baseline beats PySTEPS simultaneously on both overall MAE and overall RMSE on this held-out monsoon test set. Per protocol, **PySTEPS remains the operational nowcaster** (`OPERATIONAL_NOWCASTER=PySTEPS`, `OPERATIONAL_FUSION_PROVIDER=NONE`). We do not force a fusion win.
3. **Physical Horizon Transition Observed**: At +30 min, optical flow (pySTEPS) provides superior localized advection. Beyond +90 min, pySTEPS optical flow experiences advection dispersion, while GFS provides synoptic stability. Fusing them balances early detail with late-horizon bounds.
4. **Deep Model Status**: `ConvLSTM_V2` remains an experimental deep model with unvalidated GPU checkpoint; zero synthetic skill was fabricated.
5. **Gating Model Scaffolding**: `GateFeatureBuilder` and `SupervisedGatingBaseline` are fully implemented with unit tests. `LEARNED_GATE_TRAINED=false` because GFS replay has not yet been acquired for train/validation splits, preventing leakage-free supervised training.

## 5. Status Block
```ini
PHASE_4B_GFS_BENCHMARK_COMPLETE=true
GFS_STANDALONE_EVALUATED=true
UNIFIED_FORECAST_PROVIDER_READY=true
FIXED_FUSION_BASELINES_READY=true
SKILL_DERIVED_FUSION_READY=true
LEARNED_GATE_INFRA_READY=true
LEARNED_GATE_TRAINED=false
FUSION_HELDOUT_EVALUATED=true
PROBABILISTIC_FOUNDATION_READY=true
OPERATIONAL_FUSION_PROVIDER=NONE
OPERATIONAL_NOWCASTER=PySTEPS
PHASE_4B_COMPLETE=true
```
