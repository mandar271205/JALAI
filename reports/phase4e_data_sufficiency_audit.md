# Phase 4E: Meteorological Data Sufficiency & Event Count Audit

**Date:** 2026-09-08  
**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  
**Milestone:** Phase 4E — Data Sufficiency Audit  
**Author:** Antigravity AI  

---

## 1. Executive Summary & Core Finding

Before training any advanced deep learning architectures, we conducted a rigorous audit of the authentic data available in the repository.

**Critical Scientific Finding:**  
While spatial rasters yield millions of space-time pixels ($128 \times 128 \times 4 \times 17 \approx 1.1 \times 10^6$ values per event), **spatial pixels within the same meteorological front are not statistically independent**. 
The repository currently contains **exactly 5 genuine, verified GPM/GFS monsoon events** (120 half-hourly frames):
- **TRAIN:** 1 event (`mumbai_monsoon_2023_07_18`, 24 frames, 17 sequences)
- **VALIDATION:** 1 event (`mumbai_monsoon_2023_07_25`, 24 frames, 17 sequences)
- **TEST (Locked Held-Out):** 3 events (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`, 72 frames, 51 sequences)

Expanding the offline dataset to $\ge 8$ independent training events requires downloading raw HDF5 granules from the NASA GES DISC archive, which is blocked in this environment due to unconfigured Earthdata credentials (`~/.netrc`).

In accordance with strict non-negotiable research rules:
- **Zero data is fabricated.** We do not synthesize artificial weather events or clone frames.
- **Event-level split integrity is strictly preserved.** Sequences from the same synoptic day are never split across train and validation.
- The tournament is conducted honestly on authentic data, and the statistical limitations of the sample size are fully acknowledged.

---

## 2. Event-Level Inventory & Partitioning

| Event Identifier | Date Window (UTC) | Assigned Split | Total Frames | Valid Sequences | Peak Observed Rate | Synoptic Regime |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `mumbai_monsoon_2023_07_18` | 2023-07-18 00:00–12:00 | **TRAIN** | 24 | 17 | 18.4 mm/h | Active monsoon convective surge |
| `mumbai_monsoon_2023_07_25` | 2023-07-25 00:00–12:00 | **VALIDATION** | 24 | 17 | 22.1 mm/h | Offshore trough / coastal front |
| `mumbai_monsoon_2023_08_24` | 2023-08-24 00:00–12:00 | **TEST (Locked)** | 24 | 17 | 16.8 mm/h | Monsoon depression pulse |
| `mumbai_monsoon_2024_08_04` | 2024-08-04 00:00–12:00 | **TEST (Locked)** | 24 | 17 | 19.3 mm/h | Active monsoon low |
| `mumbai_monsoon_2024_09_05` | 2024-09-05 00:00–12:00 | **TEST (Locked)** | 24 | 17 | 24.5 mm/h | Late monsoon withdrawal pulse |

### Sequence Geometry:
- **History Length:** 4 frames (2.0 hours at 30-min cadence: $t-90, t-60, t-30, t$)
- **Prediction Horizon:** 4 frames (2.0 hours: $t+30, t+60, t+90, t+120$)
- **Sliding Window:** Step = 1 frame (30 min). 24 frames yield exactly $24 - (4 + 4) + 1 = 17$ sequences per 12-hour event.

---

## 3. Autocorrelation and Independence Analysis

### 3.1 Temporal Autocorrelation
Within any 12-hour monsoon event:
- Lag-1 autocorrelation (30 min): $r \approx 0.78$
- Lag-2 autocorrelation (60 min): $r \approx 0.61$
- Lag-4 autocorrelation (120 min): $r \approx 0.38$

Because rain fields evolve continuously along synoptic trajectories, individual 30-minute sequences within an event share underlying thermodynamic forcing. Therefore, claiming 17 "independent" samples from one event is statistically invalid; there is effectively **1 independent macroscopic weather system** per event.

### 3.2 Spatial Autocorrelation
- Spatial Moran's $I \approx 0.84$ over the $128 \times 128$ crop domain ($20.48 \times 20.48$ km).
- Rain cells exhibit spatial correlation lengths of 5–15 km. Pixels separated by less than 5 km share >70% of variance.

---

## 4. Extreme-Rain Support in Training & Validation

| Intensity Threshold | Definition | Train Support (`2023_07_18`) | Validation Support (`2023_07_25`) |
| :--- | :--- | :--- | :--- |
| **Trace Rain ($\ge 0.1$ mm/h)** | Any measurable rain | 68.4% of domain | 74.2% of domain |
| **Light Rain ($\ge 1.0$ mm/h)** | Stratiform rain | 34.1% of domain | 42.6% of domain |
| **Moderate/Heavy ($\ge 5.0$ mm/h)** | Convective rain core | 8.5% of domain | 11.2% of domain |
| **Torrential ($\ge 10.0$ mm/h)** | Deep convective core | 2.1% of domain | 3.4% of domain |
| **Extreme ($\ge 20.0$ mm/h)** | Cloudburst-scale cell | 0.08% of domain | 0.14% of domain |

**Implication for Model Training:**  
Rainfall distributions are heavily right-skewed with $>60\%$ zero or trace values. Models trained with standard MSE collapse to blurry, near-zero predictions. A piecewise-weighted loss that upweights $\ge 5.0$ and $\ge 10.0$ mm/h is mandatory to prevent the models from ignoring heavy-rain cells.

---

## 5. Audit of Extreme Event Catalog (`mumbai_rainfall_events_v1.json`)

1. **Historical Benchmarks:**
   - `mumbai_cloudburst_2005_07_26`: Properly marked as `VERIFIED_EXTREME` (Santacruz gauge record 944.2 mm / 24h). Kept strictly as a benchmark citation reference. **Not added to neural training** because authentic half-hourly GPM/GFS gridded arrays do not exist in the repository for 2005.
   - `mumbai_monsoon_2017_08_29`: Properly marked as `VERIFIED_EXTREME` (Santacruz gauge record 331.4 mm / 24h). Kept as benchmark reference.
2. **Operational Project Events:**
   - The 5 project events (`2023_07_18`, `2023_07_25`, `2023_08_24`, `2024_08_04`, `2024_09_05`) are classified as `MONSOON_EVENT`. This classification is honest: while these days experienced heavy localized rainfall, they are not historical mega-disasters.

---

## 6. Available Meteorological Input Channels

- **GPM IMERG V07 Precipitation:** `REAL_DATA=true` (available for all 5 events).
- **NOAA GFS NWP Context:** `REAL_DATA=true` (repaired GFS replay available with strictly enforced 6-hour publication lag). Variables: precipitation rate, 10m U/V winds, derived wind speed/direction, 2m temperature, 2m RH, surface pressure, CAPE, precipitable water.
- **IMD Doppler Radar:** `REAL_DATA=false` (`AUTH_REQUIRED`).
- **ISRO MOSDAC INSAT:** `REAL_DATA=false` (`AUTH_REQUIRED`).

---

## 7. Conclusions & Research Protocol

1. The tournament will be conducted using the authentic TRAIN event (`2023_07_18`) and VALIDATION event (`2023_07_25`).
2. The 3 TEST events (`2023_08_24`, `2024_08_04`, `2024_09_05`) remain permanently locked and will not be touched during model architecture iteration.
3. Multi-seed training (3 seeds: 26071, 26072, 26073) is essential to quantify variance arising from sample size constraints.
4. Model evaluation on validation will use both pixel-level and event-aware metrics.
