# Phase 4B: GFS Standalone Benchmark Evaluation

## Executive Summary
- **Dataset / Benchmark**: `mumbai_locked_test_51_v1` (51 held-out test samples)
- **Model**: NOAA Global Forecast System (GFS) 0.25° NWP (PRATE mean rate)
- **Availability Latency Assumed**: 6 hours operational lag
- **Native Cadence**: 60 minutes; **Disaggregated Cadence**: 30 minutes
- **Evaluated Horizons**: +30 min, +60 min, +90 min, +120 min
- **Common Valid Cells Evaluated**: 13,026,624 / 13,026,624 (100.0%)

## Continuous Verification (Overall & By Lead Time)

| Lead Time | Horizon (min) | MAE (mm/h) | RMSE (mm/h) | Mean Bias (mm/h) | Valid Cells |
|:---:|:---:|:---:|:---:|:---:|:---:|
| +1 | +30m | 1.2893 | 1.9816 | 0.7912 | 3,256,656 |
| +2 | +60m | 1.2361 | 1.8734 | 0.7186 | 3,256,656 |
| +3 | +90m | 1.1601 | 1.6927 | 0.6393 | 3,256,656 |
| +4 | +120m | 1.0923 | 1.5151 | 0.5350 | 3,256,656 |
| **Overall** | **All Leads** | **1.1945** | **1.7746** | **0.6710** | **13,026,624** |

## Categorical Skill Across Thresholds

| Lead Time | Threshold | POD | FAR | CSI | F1 | Frequency Bias | Hits | Misses | False Alarms |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| +30m | 0.1 mm/h | 1.0000 | 0.2560 | 0.7440 | 0.8532 | 1.3441 | 2,422,948 | 0 | 833,708 |
| +30m | 1.0 mm/h | 0.8125 | 0.4250 | 0.5076 | 0.6734 | 1.4131 | 1,042,494 | 240,560 | 770,587 |
| +30m | 5.0 mm/h | 0.1282 | 0.9521 | 0.0361 | 0.0698 | 2.6754 | 10,152 | 69,047 | 201,740 |
| +30m | 10.0 mm/h | insufficient_support | 1.0000 | insufficient_support | insufficient_support | insufficient_support | 0 | 0 | 30,739 |
| +60m | 0.1 mm/h | 0.9991 | 0.2485 | 0.7510 | 0.8578 | 1.3294 | 2,445,721 | 2,242 | 808,693 |
| +60m | 1.0 mm/h | 0.7879 | 0.4300 | 0.4942 | 0.6615 | 1.3823 | 1,013,910 | 272,940 | 764,883 |
| +60m | 5.0 mm/h | 0.0533 | 0.9781 | 0.0158 | 0.0311 | 2.4277 | 3,783 | 67,234 | 168,624 |
| +60m | 10.0 mm/h | insufficient_support | 1.0000 | insufficient_support | insufficient_support | insufficient_support | 0 | 0 | 28,880 |
| +90m | 0.1 mm/h | 0.9985 | 0.2373 | 0.7619 | 0.8648 | 1.3091 | 2,480,535 | 3,710 | 771,637 |
| +90m | 1.0 mm/h | 0.7661 | 0.4326 | 0.4836 | 0.6520 | 1.3501 | 989,058 | 302,019 | 753,982 |
| +90m | 5.0 mm/h | 0.0352 | 0.9830 | 0.0116 | 0.0229 | 2.0688 | 2,153 | 59,063 | 124,490 |
| +90m | 10.0 mm/h | insufficient_support | 1.0000 | insufficient_support | insufficient_support | insufficient_support | 0 | 0 | 14,330 |
| +120m | 0.1 mm/h | 0.9960 | 0.2229 | 0.7747 | 0.8731 | 1.2816 | 2,520,523 | 10,130 | 722,771 |
| +120m | 1.0 mm/h | 0.7188 | 0.4435 | 0.4570 | 0.6273 | 1.2918 | 935,712 | 365,982 | 745,799 |
| +120m | 5.0 mm/h | 0.0342 | 0.9735 | 0.0151 | 0.0298 | 1.2916 | 2,004 | 56,613 | 73,703 |
| +120m | 10.0 mm/h | insufficient_support | None | insufficient_support | insufficient_support | insufficient_support | 0 | 0 | 0 |

## Scientific Interpretation & Findings
1. **Spatial Scale Mismatch**: GFS operates natively on a 0.25° (~27 km) grid, resulting in spatially smooth precipitation fields that underestimate localized convective cell peaks but provide synoptic broad-scale rainfall coverage.
2. **Timing & Latency**: With the conservative 6-hour operational availability assumption, GFS cycles are 6 to 12 hours old at issue time. Despite forecast age, GFS maintains relatively stable error growth across the +30 to +120 min horizon compared to optical flow extrapolation.
3. **Role in Fusion**: GFS is complementary to radar nowcasting — while radar/pySTEPS excels at +30 min, its skill decays sharply by +120 min where NWP physics can regularize extrapolation errors.

## Audit Provenance
- **Benchmark Manifest**: `data/processed/benchmarks/mumbai_locked_test_51_v1.json`
- **Replay Directory**: `data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1`
- **Evaluation Output JSON**: `reports/phase4_gfs_standalone_evaluation.json`
