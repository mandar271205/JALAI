# Phase 4C: Supervised Learned Gating Model Training Report

**Date**: 2026-09-08T14:32:22.128862+00:00  
**Model Architecture**: `LearnedGateMLP` (Linear(44, 32) -> ReLU -> Dropout(0.05) -> Linear(32, 16) -> ReLU -> Linear(16, 4) -> Masked Softmax)  
**Total Parameters**: 2,036  
**Formulation**: OPTION B — Direct Convex Provider Weight Optimization ($w_i \ge 0, \sum w_i = 1$)  
**Optimization Objective**: Spatial Mean Absolute Error (MAE) under intersection valid mask  
**Split Isolation**: Trained strictly on `mumbai_monsoon_2023_07_18` (Train), early-stopped on `mumbai_monsoon_2023_07_25` (Validation).  
**Held-Out Test Status**: Untouched.  

---

## 1. Training Summary
- **Input Dimension**: 44 features (lead time, current rainfall, regime, GFS forecast age, provider forecasts, ensemble statistics).
- **Training Samples**: 68 issue-horizon pairs (3,274,378 valid space-time cells).
- **Validation Samples**: 68 issue-horizon pairs (3,461,097 valid space-time cells).
- **Best Epoch**: 25 / 40
- **Best Validation MAE**: **0.9302 mm/h**
- **Model Checksum**: `6387077de055b322964a445695e09b4ca15fdb7a358339e8dff65a8b6442063b`

---

## 2. Learned Provider Weight Distribution on Validation Split
- `pysteps`: **0.0957**
- `gfs`: **0.3829**
- `persistence`: **0.5215**
- `convlstm_v2`: **0.0000** (unavailable, masked to 0)

---

## 3. Training Dynamics
| Epoch | Train MAE (mm/h) | Val MAE (mm/h) | Val RMSE (mm/h) | PySTEPS Weight | GFS Weight | Persistence Weight |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 1.5597 | 0.9431 | 1.2819 | 0.359 | 0.300 | 0.341 |
| 5 | 1.4981 | 0.9490 | 1.2890 | 0.353 | 0.288 | 0.359 |
| 9 | 1.4454 | 0.9496 | 1.2889 | 0.333 | 0.286 | 0.381 |
| 13 | 1.3987 | 0.9420 | 1.2768 | 0.286 | 0.305 | 0.409 |
| 17 | 1.3631 | 0.9390 | 1.2687 | 0.228 | 0.318 | 0.454 |
| 21 | 1.3241 | 0.9388 | 1.2643 | 0.168 | 0.331 | 0.501 |
| 25 | 1.2903 | 0.9302 | 1.2489 | 0.096 | 0.383 | 0.521 |
| 29 | 1.2543 | 0.9403 | 1.2599 | 0.054 | 0.383 | 0.562 |
| 33 | 1.2359 | 0.9407 | 1.2524 | 0.026 | 0.447 | 0.527 |
| 37 | 1.2260 | 0.9503 | 1.2629 | 0.015 | 0.463 | 0.522 |
