# Phase 3 ConvLSTM Training Report

## Current Status

- Implementation status: complete and locally verified
- Genuine real-data GPU training: not run
- Local verification: full-size CPU forward pass plus checkpoint/resume unit test
- Test suite: 35 passed, 2 existing/environment warnings
- Best production checkpoint: none
- Held-out ConvLSTM metrics: not available
- `PHASE_3_MODEL_VALIDATED=false`

## Implemented Training Design

The model accepts `[batch, time, channels, height, width]` and emits four
deterministic, non-negative rainfall fields for +30, +60, +90, and +120
minutes. The compact ConvLSTM encoder uses a separate prediction head so a
future probabilistic head can be added without changing the dataset or model
provider boundary.

Rainfall is transformed as `log1p(rainfall) / P99.5(log1p(training rainfall))`.
The scale is fitted only from valid pixels in whole training events. The loss
is weighted MAE plus 0.25 times weighted MSE; pixels at or above 5 mm/h receive
up to four additional units of weight. Missing pixels are excluded explicitly.

The training loop provides deterministic seeds, validation, best/latest
checkpoints, resume, early stopping, gradient clipping, AdamW, ReduceLROnPlateau,
CPU/CUDA selection, and JSON/CSV history.

The prepared corpus currently has 72 frames and 17 sequences in each whole-event
split. It is intentionally not treated as a scientifically adequate validation
corpus. This report must be updated only after a genuine Colab GPU run on an
approved expanded dataset. Loss values from
unit tests or CPU smoke tests are engineering checks, not model-skill metrics.
