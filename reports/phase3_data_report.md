# Phase 3 Training-Data Report

## Dataset

- Data version: `gpm_imerg_v07_mumbai_monsoon_windows_v1`
- Source: NASA GPM IMERG Final Run Half-Hourly (IMERG_V07)
- Native cadence: 30 minutes
- Source resolution: 0.1 deg (~11 km)
- Canonical resolution: ~161m @ 256x256
- Events/days: 3 / 3
- Frames: 72 actual / 72 expected
- Preserved raw source files: 72 (0.5447 GiB)
- Temporal missing: 0.0000%
- Pixel missing: 2.5635%

## Event-Isolated Splits

- `mumbai_monsoon_2023_07_18` (train): 24/24 frames, 2023-07-18T00:00:00+00:00 to 2023-07-18T11:30:00+00:00
- `mumbai_monsoon_2023_07_25` (validation): 24/24 frames, 2023-07-25T00:00:00+00:00 to 2023-07-25T11:30:00+00:00
- `mumbai_monsoon_2023_08_24` (test): 24/24 frames, 2023-08-24T00:00:00+00:00 to 2023-08-24T11:30:00+00:00

## Rainfall Distribution

- Minimum / mean / maximum: 0.0000 / 2.5129 / 16.9801 mm/h
- P50 / P90 / P95 / P99: 1.9808 / 5.7569 / 6.8921 / 8.5797 mm/h
- Standard deviation: 2.2471 mm/h
- Percentile sample size: 656805

| Threshold (mm/h) | Valid-pixel fraction | Frames containing event |
|---:|---:|---:|
| 0.1 | 0.826699 | 1.000000 |
| 1.0 | 0.695554 | 0.958333 |
| 5.0 | 0.149724 | 0.472222 |

All splits are whole events. Adjacent windows are never randomly divided across train, validation, and test.

## Limitation

This 72-frame, three-window corpus is sufficient to exercise the complete training pipeline and event-aware split logic, but it is still too small for a scientifically meaningful rainfall-nowcast validation. Expand the bounded event list deliberately before the real Colab GPU training campaign.
