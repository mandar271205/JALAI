# Phase 4E: Deep Nowcasting Training & Architecture Report

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4E — Neural Architecture Tournament  
**Author:** Antigravity AI  

---

## 1. Executive Summary & Experimental Design

Phase 4E establishes a scientifically rigorous, multi-architecture deep learning nowcasting tournament for coastal urban rainfall over Mumbai.

To guarantee scientific fairness and eliminate benchmark contamination:
1. **Identical Data Partitioning:** All architectures were trained on the exact same authentic training dataset (`mumbai_monsoon_2023_07_18`, 17 sequences) and evaluated during model selection on the exact same validation dataset (`mumbai_monsoon_2023_07_25`, 17 sequences).
2. **Untouched Held-Out Test Events:** The 3 locked test events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`, 51 sequences) were strictly held out until model architecture, hyperparameters, and checkpoints were frozen.
3. **Multi-Seed Protocol:** Every neural model was trained across 3 distinct random seeds (`26071`, `26072`, `26073`) to quantify parameter initialization variance.
4. **Common Multi-Scale Objective:** All models optimized the exact same loss function (`MultiScalePiecewiseLoss`).

---

## 2. Neural Architectures Evaluated

### 2.1 ConvLSTM V3 (`ConvLSTMNowcasterV3`)
- **Philosophy:** Spatiotemporal autoregression with explicit multi-source projection and residual persistence skip.
- **Components:**
  - `MultiSourceEncoder`: $1 \times 1$ convolution mapping 3 input channels to 16 hidden channels.
  - `ConvLSTM`: 2-layer convolutional LSTM with $3 \times 3$ kernels and hidden channels `(16, 16)`.
  - `Lead-Specific Heads`: 4 dedicated $3 \times 3$ convolutional decoder heads predicting lead offsets at +30, +60, +90, and +120 minutes.
  - `Residual Formulation`: $\hat{Y}_{t+h} = \text{ReLU}(Y_t + \Delta Y_{t+h})$.
- **Parameter Count:** 113,708 parameters.

### 2.2 U-Net + ConvGRU (`UNetConvGRUNowcaster`)
- **Philosophy:** Multi-scale spatial feature encoding with temporal bottleneck and multi-level skip connections.
- **Components:**
  - `Spatial Encoder`: 3-level hierarchical encoder ($128 \times 128 \to 64 \times 64 \to 32 \times 32$) with channels 8, 16, 32.
  - `ConvGRU Bottleneck`: Spatiotemporal recurrent bottleneck operating on the $32 \times 32$ feature map with 32 channels.
  - `Spatial Decoder`: Bilinear upsampling and skip-connection concatenations restoring the $128 \times 128$ resolution.
  - `Lead-Specific Heads`: 4 distinct prediction heads from decoded multi-scale features.
- **Parameter Count:** 228,820 parameters.

### 2.3 Spatiotemporal Attention Nowcaster (`STAttentionNowcasterV1`)
- **Philosophy:** Compact patch-based vision transformer for spatiotemporal precipitation dynamics.
- **Components:**
  - `Patch Embedding`: $8 \times 8$ non-overlapping spatial patches mapped to embedding dimension 32 ($16 \times 16 = 256$ spatial tokens).
  - `Spatial Self-Attention`: Multi-head self-attention across spatial patches at each time step (num_heads = 2).
  - `Cross-Time Attention`: Temporal self-attention modeling motion trajectories across the 4 history frames.
  - `Patch Reconstruction Decoder`: Unfolds tokens back to $128 \times 128$ feature space.
  - `Lead-Specific Heads`: 4 dedicated output convolutions.
- **Parameter Count:** 134,620 parameters.

---

## 3. Training Hyperparameters & Loss Objective

### Common Training Settings:
- **Optimizer:** AdamW (`lr=1e-3`, `weight_decay=1e-4`, `betas=(0.9, 0.999)`)
- **Learning Rate Schedule:** CosineAnnealingLR (`T_max=10`, `eta_min=1e-5`)
- **Batch Size:** 2 (due to memory constraints and sequence length)
- **Epochs:** Up to 10 with Early Stopping (patience = 3 based on validation MAE)
- **Gradient Clipping:** Max norm = 1.0

### Multi-Scale Piecewise Loss:
$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{native}} + \lambda_{\text{coarse}} \mathcal{L}_{\text{coarse}}$$
- **Native Loss:** Weighted piecewise MAE with threshold multiplier:
  - $< 1$ mm/h: $1.0\times$
  - $1 - 5$ mm/h: $2.0\times$
  - $5 - 10$ mm/h: $3.5\times$
  - $\ge 10$ mm/h: $5.0\times$
  - Huber loss component: weight $0.05$.
- **Coarse Loss:** Average pooling ($2 \times 2$) to penalize larger spatial displacement: $\lambda_{\text{coarse}} = 0.25$.

---

## 4. Checkpoint & Artifact Registry

Model checkpoints and manifests are preserved under:
- `models/nowcast/convlstm_v3/`
- `models/nowcast/unet_convgru_v1/`
- `models/nowcast/st_attention_nowcaster_v1/`

Each directory contains:
- `best_checkpoint_seed_<seed>.pt`
- `training_history_seed_<seed>.json`
- `config_snapshot.yaml`
- `model_metadata.json` (including SHA-256 checkpoint hashes)
