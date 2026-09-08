# Phase 3 V2 Heavy-Rain ConvLSTM Design

## Status

- `PHASE_2_READY=true`
- `PHASE_3_IMPLEMENTATION_READY=true`
- `PHASE_3_GPU_PIPELINE_VERIFIED=true` (V1 evidence supplied in the handoff)
- `PHASE_3_V2_IMPLEMENTATION_READY=true`
- `PHASE_3_MODEL_VALIDATED=false`
- `PHASE_4_STARTED=false`

V2 must not be described as validated until a genuine GPU training run and the
mask-aware three-way evaluation complete on the untouched held-out test events.

## Why V1 Did Not Pass the Model Gate

The supplied held-out benchmark shows that V1 underperformed both baselines on
continuous error. Overall MAE/RMSE were 0.6584/1.0396 for Persistence,
0.6192/0.9752 for PySTEPS, and 0.8561/1.2136 for ConvLSTM V1. At 5 mm/h and +30
minutes, V1 reached POD 0.4273 but FAR 0.6846 and CSI 0.2217; its 5 mm/h POD fell
to zero at +60, +90, and +120 minutes. The model therefore did not retain useful
heavy-rain skill across the required forecast horizon.

## V2 Changes

The `convlstm_mumbai_heavyrain_v2` model predicts a signed residual in physical
mm/h. Each horizon is reconstructed as the latest observed rainfall plus the
predicted residual, followed by a zero lower bound. The final residual head is
zero-initialized, so an untrained V2 starts exactly at Persistence.

Inputs retain the train-only `log1p` normalization used by V1. Targets, loss
weight boundaries, reconstructed predictions, and validation metrics use
physical mm/h. The loss applies configured piecewise weights of 1, 2, 6, and 10
at 1, 5, and 10 mm/h, masks every term with `target_mask`, and divides by the
sum of valid pixel weights.

The optional `WeightedRandomSampler` is restricted to training sequences. A
sequence weight is derived only from that sequence's target frames, using
configurable weights 1, 2, 4, and 6 at target maxima of 1, 5, and 10 mm/h.
Validation and test loaders remain deterministic and unweighted.

Every validation epoch pools MAE, RMSE, and TP/FP/FN/TN at 0.1, 1.0, and 5.0
mm/h over valid cells. Best-checkpoint selection maximizes a configurable score
that rewards lower MAE and higher 5 mm/h CSI/POD while penalizing FAR. Missing
5 mm/h observations are handled without NaN checkpoint decisions. Checkpoints
and `training_metadata.json` store the best score, metrics, and epoch.

The official evaluator intersects `target_mask` with finite observations and all
three provider outputs, then applies that identical comparison mask to
Persistence, PySTEPS, and ConvLSTM. Baseline forecasting logic is unchanged.

## Dataset Contract and Limitations

V2 expects the existing versioned corpus at
`data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1`. It does not
invoke acquisition or redownload the 432 source frames. That expanded version is
not present in this local repository snapshot, so local V2 engineering tests use
synthetic fixture stores and the production commands fail closed until the real
versioned manifest/stores are mounted at the expected path.

The split contract remains:

- train: `mumbai_monsoon_2023_07_18`
- validation: `mumbai_monsoon_2023_07_25`
- test: `mumbai_monsoon_2023_08_24`

The source GPM IMERG grid is approximately 0.1 degree, or roughly 11 km. Its
resampling to the 256x256 canonical Mumbai grid does not create new spatial
detail, so neighborhood-scale interpretation and apparent sharpness must not be
mistaken for higher-resolution observations.

## Production Commands

Train on a CUDA runtime:

```bash
python scripts/train_convlstm.py --config configs/training/convlstm_mumbai_heavyrain_v2.yaml --device cuda
```

Resume from the V2 latest checkpoint:

```bash
python scripts/train_convlstm.py --config configs/training/convlstm_mumbai_heavyrain_v2.yaml --device cuda --resume models/nowcast/convlstm_mumbai_heavyrain_v2/latest.pt
```

Run mask-aware three-way held-out evaluation:

```bash
python scripts/evaluate_phase3.py --config configs/training/convlstm_mumbai_heavyrain_v2.yaml --checkpoint models/nowcast/convlstm_mumbai_heavyrain_v2/best.pt --device cuda
```
