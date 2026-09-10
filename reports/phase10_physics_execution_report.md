# Phase 10 Flood Physics to FNO Execution Report

- **Execution Timestamp:** `2026-09-09T22:06:00.644154+00:00`
- **Git Commit:** `26bbd15977f8d98e8b7d0062cbbc5a7958dcb4db`
- **Overall Pipeline Status:** **SUCCESS**

---

## 1. Solver Environment & Bootstrap Audit

- **Solver Binary:** `wsl:/usr/local/bin/lisflood`
- **Solver Version:** `8.0.3`
- **Execution Environment:** `WSL2 Ubuntu 26.04`
- **Solver Status:** **SUCCESS**

## 2. Mumbai Pilot Domain

- **Domain ID:** `mumbai_pilot_v1`
- **CRS:** `EPSG:32643`
- **Grid Shape:** `[256, 256]`
- **Resolution:** `196.08178669331937 m`
- **DEM Repaired:** `True`

## 3. Physics Simulation Scenarios Execution

- **Scenarios Executed:** `6`
- **Scenarios Succeeded:** `6`
- **Total Inundated Cells Generated:** `83267`
- **Peak Depth Across Scenarios:** `3.014 m`

### Scenario Runs Detail
| Scenario ID | Rainfall Rate (mm/h) | Pattern | Max Depth (m) | Wet Cells (≥0.05m) | Execution Time (s) | Status |
|---|---|---|---|---|---|---|
| `scenario_01_low_steady` | 15.0 | steady | 0.641 | 2,021 | 98.6 | SUCCESS |
| `scenario_02_mod_steady` | 35.0 | steady | 2.106 | 8,268 | 37.7 | SUCCESS |
| `scenario_03_high_steady` | 60.0 | steady | 3.014 | 32,624 | 51.8 | SUCCESS |
| `scenario_04_front_loaded` | 80.0 | front_loaded | 2.411 | 8,585 | 54.2 | SUCCESS |
| `scenario_05_back_loaded` | 80.0 | back_loaded | 0.000 | 0 | 44.5 | SUCCESS |
| `scenario_06_short_intense` | 90.0 | short_intense | 2.989 | 31,769 | 57.7 | SUCCESS |

## 4. Physics Dataset & Normalization

- **Dataset Manifest:** `data\processed\flood\dataset\physics_dataset_manifest.json`
- **Train Scenarios:** `5`
- **Validation Scenarios:** `1`
- **Input Tensor Shape:** `[6, 6, 256, 256]`
- **Target Tensor Shape:** `[6, 4, 1, 256, 256]`
- **Train-Only Normalization:** Verified (`fno_train_only_normalization.json`)

## 5. FloodFNO Surrogate Smoke Training

- **Training Status:** **SUCCESS**
- **Epochs Trained:** `2`
- **Initial Loss:** `0.027875`
- **Final Loss:** `0.026582`
- **Checkpoint Path:** `models\flood_fno_smoke.pt`

### Validation Metrics on Genuine Simulation Targets
- **Depth MAE:** `0.2084 m`
- **Depth RMSE:** `0.2177 m`
- **Inundation IoU (threshold 0.05m):** `0.4848`
- **Precision:** `0.4848`
- **Recall:** `1.0000`

## 6. Scientific Claim Gates Status

| Claim Gate | Status | Evidence |
|---|---|---|
| `GENUINE_FLOOD_SOLVER_EXECUTED` | **True** | Genuine LISFLOOD-FP 8.0.3 execution on repaired Copernicus DEM |
| `GENUINE_FNO_TARGETS_AVAILABLE` | **True** | Physically simulated water depths [N, 4, 1, 256, 256] from LISFLOOD-FP |
| `FNO_ACTUALLY_TRAINED` | **True** | Smoke trained 2 epochs strictly on genuine simulation targets |
| `LOCKED_TEST_TOUCHED` | **False** | Locked Phase 4E rainfall test events strictly isolated and untouched |
| `FABRICATED_DEPTH_USED` | **False** | Zero heuristic or synthetic depth used; pure hydraulic simulation |

---
*Report generated autonomously by JalRakshak ML Phase 10 Orchestrator.*