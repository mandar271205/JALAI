# Phase 4E: Empirical Failure Modes & Meteorological Diagnostics

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4E — Diagnostic Failure Analysis  
**Author:** Antigravity AI  

---

## 1. Executive Summary

A critical requirement of scientific research is transparently identifying, categorizing, and diagnosing model failure modes. In nowcasting over coastal megacities like Mumbai, errors are not simply uniform Gaussian noise; they exhibit systematic meteorological pathology.

We conducted diagnostic evaluations across both the validation event (`mumbai_monsoon_2023_07_25`) and the locked held-out test events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`) to isolate the primary failure mechanisms of deep nowcasting architectures.

---

## 2. Taxonomy of Observed Failure Modes

### Failure Mode 1: Convective Initiation (Missed Peaks)
- **Meteorological Mechanism:** Rapid in-situ convective triggering over the Thane Creek / Salsette Island boundary where sea-breeze convergence meets humid westerly monsoon flow.
- **Model Behavior:** Because input history (past 2 hours) shows low or moderate rainfall, purely autoregressive models fail to anticipate explosive cell development within 30–60 minutes.
- **Impact:** Low POD for extreme thresholds ($\ge 10$ mm/h) during the onset phase of sudden storms.

### Failure Mode 2: Rapid Convective Cell Decay (False Alarms)
- **Meteorological Mechanism:** Deep convective cores collapsing upon encountering cold storm downdrafts or moving inland over the Western Ghats crest.
- **Model Behavior:** ConvLSTM and U-Net ConvGRU architectures propagate the high-intensity core forward in space along estimated advection vectors, over-forecasting rainfall downstream where the cell had actually dissipated.
- **Impact:** Elevated FAR (False Alarm Rate) at +90 and +120 minutes for heavy rainfall thresholds.

### Failure Mode 3: Spatial Displacement / Phase Errors
- **Meteorological Mechanism:** Fast-moving monsoon squalls traversing Mumbai at 25–40 km/h.
- **Model Behavior:** The predicted rainband is geographically displaced by 5–15 km relative to actual radar/satellite centroid observations.
- **Impact:** Pointwise MAE and RMSE penalize displaced rain cells twice (a miss where it rained, and a false alarm where it did not), a well-known "double-penalty" phenomenon in high-resolution verification. Multi-scale pooled loss partially mitigates this.

### Failure Mode 4: Long-Horizon Variance Collapse & Blur
- **Meteorological Mechanism:** Increasing forecast uncertainty at +90 and +120 minutes.
- **Model Behavior:** Under $L_1$ and $L_2$ regression objectives, the conditional expectation converges toward a blurred spatial mean. Fine convective structures dissolve into widespread light-to-moderate rain.
- **Impact:** Sharp decline in CSI for heavy rain ($\ge 5$ mm/h) beyond 60 minutes.

### Failure Mode 5: GFS NWP Spatial Coarseness Artifacts
- **Meteorological Mechanism:** GFS forecasts have a native grid of 0.25° (~27 km), which is bilinearly interpolated to the 0.1° / 128x128 canonical grid.
- **Model Behavior:** The coarse GFS precipitation channel acts as a low-frequency envelope. When the model relies heavily on GFS, it struggles to resolve urban-scale localized bursts.

---

## 3. Diagnostic Visualizations

Generated diagnostic maps and artifact references:
- **Spatial Error Maps:** `reports/figures/10_error_maps.png` (displays pointwise residuals $\hat{Y} - Y$).
- **Representative Failure Cases:** `reports/figures/11_failure_cases.png` (illustrating missed initiation, false alarms, and cell dissipation).
- **Skill Degradation Profiles:** `reports/figures/03_skill_vs_lead_time.png` and `reports/figures/04_heavy_rain_csi_vs_lead.png`.

---

## 4. Engineering & Scientific Mitigations

1. **Residual Persistence Formulation:** Forcing the network to predict residual deltas $\Delta Y_{t+h}$ over persistence prevents catastrophic baseline collapse.
2. **Multi-Scale Loss Weighting:** Evaluating coarse pooled scales ($2 \times 2$) forces the optimizer to prioritize macro rainband structure even when fine pixels undergo phase shifts.
3. **Probabilistic Ensembling:** Multi-seed ensembles capture the spread and spatial uncertainty of convective displacement, providing actionable risk intervals for downstream hydraulic models.
