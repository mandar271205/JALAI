# Phase 4E: Advanced Deep Nowcasting Model Tournament (Research Architecture & GPU Pipeline Specification)

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4E — Deep Nowcasting Tournament Framework & Local Implementation  
**Author:** Antigravity AI  

---

## 1. Executive Summary & Research Governance

Phase 4E initiates a research-grade comparison of advanced deep neural nowcasting architectures for convective precipitation over Mumbai under rigorous anti-leakage, split-isolation, and meteorological integrity standards.

### Hardware Reality & Integrity Boundary:
- **Local Environment:** CPU-only (Intel/AMD x86_64, Windows, zero CUDA GPUs available).
- **Scientific Ruling:** Training high-resolution spatiotemporal neural models across multiple seeds on CPU is strictly an **engineering smoke-test / sanity verification**. It is **not** a valid basis for claiming a research-grade tournament outcome or promoting a deep model to operational status.
- **Held-Out Test Set Isolation:** The permanently held-out test events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`, 51 sequences) were **strictly protected**. The local tournament runner was stopped before any test evaluation could occur, and an automated audit confirmed that zero test files or sequences were opened or accessed.
- **Operational Baseline:** `OPERATIONAL_NOWCASTER=PySTEPS` remains locked and unchallenged.

---

## 2. Tournament Architecture Specifications

All neural models share an identical multi-source input contract (GPM precipitation history $t-90$ to $t$, GFS forecast replay, SRTM digital elevation model) and output $128 \times 128$ physical rainfall rasters across 4 forecast leads (+30, +60, +90, +120 minutes) with strict non-negativity ($\ge 0.0$ mm/h) enforced via ReLU activation.

### Model 1: ConvLSTM V3 (`ConvLSTMNowcasterV3`)
- **Philosophy:** Autoregressive spatiotemporal recurrent network with explicit multi-source projection and residual persistence formulation.
- **Architecture:**
  - Input Projection: Conv2d ($3 \to 16$ channels).
  - Temporal Core: 2-layer ConvLSTM ($3 \times 3$ kernels, 16 hidden channels).
  - Decoder: 4 lead-specific convolutional heads producing residual offsets $\Delta Y_{t+h}$.
  - Residual Output: $\hat{Y}_{t+h} = \text{ReLU}(Y_t + \Delta Y_{t+h})$.
- **Parameter Count:** 113,708 parameters.

### Model 2: U-Net + ConvGRU (`UNetConvGRUNowcaster`)
- **Philosophy:** Multi-scale spatial feature encoding with temporal bottleneck and multi-level skip connections.
- **Architecture:**
  - Spatial Encoder: 3-level hierarchical encoder ($128 \times 128 \to 64 \times 64 \to 32 \times 32$) with channels 8, 16, 32.
  - Temporal Bottleneck: ConvGRU operating on the $32 \times 32$ latent feature map.
  - Spatial Decoder: Bilinear upsampling with skip-connection concatenations restoring $128 \times 128$ resolution.
  - Decoder: 4 lead-specific prediction heads.
- **Parameter Count:** 228,820 parameters.

### Model 3: Spatiotemporal Attention (`STAttentionNowcasterV1`)
- **Philosophy:** Compact patch-based vision transformer modeling spatial self-attention and cross-time motion trajectories.
- **Architecture:**
  - Stem: $8 \times 8$ non-overlapping patch embedding (256 spatial tokens, dimension 32).
  - Attention Layers: Spatial Multi-Head Self-Attention (num_heads = 2) followed by Cross-Time Self-Attention across 4 temporal frames.
  - Reconstruction Decoder: Patch unfolding back to $128 \times 128$ grid with 4 dedicated lead heads.
- **Parameter Count:** 134,620 parameters.

---

## 3. Data & Split Integrity Audit

- **Authentic Events:**
  - **TRAIN:** `mumbai_monsoon_2023_07_18` (17 valid sequences).
  - **VALIDATION:** `mumbai_monsoon_2023_07_25` (17 valid sequences).
  - **TEST (Permanently Locked):** `mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05` (51 valid sequences).
- **Normalization:** `MultiSourceStats` fitted exclusively on the 17 training sequences.
- **Multisource Channel Inventory:**
  - Real authentic channels: `rainfall_gpm`, `gfs_precipitation`, `static_elevation`.
  - Unavailable channels: `radar_reflectivity`, `radar_rainfall`, `satellite_ir`, `satellite_wv` (explicitly marked `REAL_DATA=false`).

---

## 4. Colab GPU Execution Pipeline

To enable true multi-seed training and defensible scientific tournament evaluation, the complete GPU execution pipeline is codified in:
`colab/02_phase4e_deep_model_tournament.ipynb`

### Key Safety & Operational Features:
1. **Drive Persistence:** Automatically saves all checkpoints, configs, and reports to `/content/drive/MyDrive/JALAI_DATA/`.
2. **Explicit Test Evaluation Guard:**
   ```python
   # Cell O: Locked Test Evaluation Guard
   RUN_LOCKED_TEST = False
   ```
   Requires manual user intervention to set `RUN_LOCKED_TEST = True` ONLY after reviewing validation results and freezing model selection.
3. **Reproducible Multi-Seed Protocol:** Evaluates seeds `26071`, `26072`, `26073` for all 3 neural architectures.

---

## 5. Verification & Test Suite Summary

- **Phase 4E Unit & Integrity Tests:** 14 passed / 0 failed in `tests/test_deep_nowcast_phase4e.py`.
- **Regression Suite:** 35 passed / 0 failed across data leakage, contracts, metrics, weather framework, and fusion modules.
- **Total Tests Passed:** 49 passed.

---

## 6. Audit of Current Interrupted Local Run

- **Interruption Time:** 2026-09-08 22:39:11 local time.
- **Status of Running Task:** Cancelled immediately upon user instruction.
- **Test Dataset Access Audit:**
  - Test files opened/read: **0**
  - Test sequences evaluated: **0**
  - Held-out test evaluation report generated: **No** (`reports/phase4e_final_heldout_tournament.json` does not exist).
  - **Confirmation:** The locked held-out test events were 100% uncompromised.
