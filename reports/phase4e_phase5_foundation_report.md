# Phase 4E final stack and Phase 5 foundation

Date: 2026-09-09. This is a code/schema/test/readiness report. No replay, download,
normalization fit, model training, locked-test evaluation, hydraulic simulation, or FNO
training was executed.

## 1–3. Repository and takeover audit

The initial worktree was clean. The latest local commit was
`ea498af864571eb8c14421b1ca3172d169363e69`, `feat(phase4e): harden post-replay
integrity audit, real-channel audit, and train-only normalization`. Its six-file diff was
inspected. Replay integrity, real-channel population/provenance, train-only normalization,
the replay early-manifest guard, and their tests are present. The inherited relevant suite
passed: **71 passed, 31 warnings in 499.63 s**. The warnings were Zarr and Rasterio
deprecations. The only unavoidable overlap is `phase4e_prepare.py`: its execution plan and
winner gate needed downstream tournament requirements; its normalization safeguards remain.

## 4–6. Model audit, fixes, and parameter counts

The original model classes supported a legacy combined tensor, silently substituted absent
configured sources with zeros, did not enforce the final shapes, and used a hard clamp after
the persistence residual. The historical YAML files still described three channels and one
training event. They are now explicitly marked legacy. The final configuration is
`configs/training/phase4e_final_v1.yaml`.

The final-only path requires separated inputs, validates exact dimensions and finite values,
has no target argument, and uses differentiable `softplus` non-negativity without upper
clipping. Legacy calls remain only for backward compatibility outside the final runner.

Parameter counts for the exact final configuration:

| Architecture | Parameters |
|---|---:|
| ConvLSTM V3 | 121,052 |
| U-Net + ConvGRU | 236,308 |
| Compact ST-Attention | 134,204 |

All decode exactly four horizons and remain compact.

## 7–9. Tensor, dataset, and training invariants

- `obs_history [B,4,1,H,W]`: past GPM only.
- `nwp_future [B,4,11,H,W]`: exact configured order: precipitation, u10, v10,
  wind speed, wind-direction sine/cosine, t2m, rh2m, surface pressure, CAPE, PWAT.
- `static_features [B,1,H,W]`: elevation only.
- `target/output [B,4,1,H,W]`; target never enters `forward`.
- Canonical grid EPSG:32643, 256×256; final crop 128×128.
- Train has 12 events/204 issues; validation has 3 events/51 issues. The normal dataset API
  accepts only train/validation. It cannot construct test.
- Final replay and channel audits plus a final train-only normalization artifact are mandatory.
  Provisional, legacy, wrong-order, wrong-hash, validation-fitted, and test-contaminated stats
  fail closed.
- Missing GPM/NWP/static data, missing channels, NaN, Inf, negative rainfall, corrupt shapes,
  missing provenance, or target-time mismatch fail; they are not silently filled.
- Train crop derives deterministically from seed + event + issue time and is aligned across all
  tensors. Validation uses a deterministic centre crop with no augmentation.
- The runner seeds Python/NumPy/torch CPU/CUDA/DataLoader workers, supports CUDA AMP,
  GradScaler, gradient clipping, scheduler, explicit OOM microbatch logging, device metadata,
  peak VRAM, and runtime/sample/epoch/parameter reporting.
- Atomic `latest.pt` and `best.pt` are distinct. Resume requires matching architecture/model
  config/seed/config hash/normalization hash/replay hash/git commit and restores optimizer,
  scheduler, scaler, and RNG states. Early stopping monitors validation MAE only.

## 10. Loss review

`MultiScalePiecewiseLoss` remains deliberately unchanged: physical-space intensity-weighted
MAE + `0.05 × MSE`, thresholds 1/5/10 mm/h, weights 1/2/6/10, plus `0.25 ×` the same loss on
2× average-pooled fields with 75% valid-mask support. Code is in `deep_nowcast/losses.py` and
values are locked in `phase4e_final_v1.yaml`. Roles are respectively robust absolute error,
limited large-error penalty, heavy-rain emphasis, and coarse storm-structure agreement. No
locked test was used or made accessible for tuning. Selection uses common validation metrics,
not training loss.

## 11–14. Tournament, multi-seed statistics, ablations, and dropout

Common validation reports MAE/RMSE/Bias and pooled POD/FAR/CSI/F1 at 0.1/1/5/10 mm/h,
overall, per event, per horizon, and event×horizon. Each threshold records positive target
count, supporting-event count, and valid count. Fewer than 20 positives or fewer than two
supporting events is `INSUFFICIENT_SUPPORT`; categorical scores become null.

Deep runs use seeds 26071/26072/26073 and retain individual results plus mean/sample standard
deviation. Paired comparison resamples whole validation events (three units), seed 26071,
2,000 replicates, 95% percentile intervals. Pixels are never declared independent.

Pre-registered ablations are: A precipitation removed; B five-channel wind group removed;
C five-channel thermodynamic group removed; D terrain removed; E observation-only; F NWP-only.
Masks record exact withheld channels, `zero_is_mask_not_measurement=true`, and no replacement
information. Source-dropout training and missing-source stress evaluation are separately
labeled; observation, NWP, and terrain policies are supported.

## 15–16. Winner freeze and locked-test isolation

Freeze fails unless full non-test replay, replay audit, real-channel audit, final train-only
normalization, all three architectures × all three seeds, common validation tournament,
ablations, source-dropout evaluation, and a clean locked-test attestation pass. The immutable
atomic manifest records the winner, architecture, checkpoint hashes, seeds, validation metrics,
selection rule, replay and normalization hashes, audit/config hashes, git commit, timestamp,
and parameter count. Freeze never runs test and refuses overwrite.

Training, normalization, validation, ablation, early stopping, and winner selection expose no
test dataset path. A separate future test command requires a valid freeze plus explicit test
configuration; this task did not execute it.

## 17–28. Phase 5 architecture and scientific semantics

The foundation now follows: rainfall forecast → relative susceptibility → SWMM/LISFLOOD-FP
physics → immutable physics-reference dataset → FNO surrogate → exposure → vulnerability →
explicitly normalized H×E×V risk → scenario uncertainty → explanations.

- Susceptibility accepts only named, aligned, provenanced genuine rasters. It emits a
  dimensionless [0,1] relative score with `calibrated_depth=false` and refuses metre/depth
  export. It is not flood depth or inundation probability.
- `PhysicsScenario` records rainfall forcing, times/timestep, DEM, roughness, drainage,
  boundaries, infiltration, CRS/grid, provenance, and assumptions. Missing physical inputs
  return `INSUFFICIENT_PHYSICAL_INPUTS`. `PhysicsResult` records depth/extent/velocity/mask,
  solver/version/runtime/convergence/hashes, `physically_simulated`, and `calibrated`.
- SWMM preparation converts mm/h to interval depth and requires a real network. LISFLOOD-FP
  requires DEM/grid, roughness/infiltration, boundaries, executable, isolated work directory,
  and a real output parser. Both propagate missing executable, timeout, solver error, malformed
  output, and provenance. No Mumbai drainage or calibration was invented.
- Physics dataset freeze accepts only successful genuine solver depth in metres and splits by
  scenario ID. Susceptibility, heuristic, and random targets are rejected.
- Compact FNO has explicit shape contracts, differentiable nonnegative depth, train-only
  normalization hooks, and a hard gate requiring a frozen nonempty genuine physics corpus.
  Evaluation contracts cover depth MAE/RMSE, inundation IoU/CSI, peak and extent error, runtime,
  and measured-only speedup.
- Exposure retains layer CRS/type/source/version/hash, supports aligned raster intersection and
  externally supplied H3 indexing, and returns unavailable instead of inventing counts.
- Vulnerability remains separate, requires sourced normalized factors/curves and uncertainty,
  and reports partial when factors are missing.
- Risk uses configured component scales before H×E×V composition; it returns raw/normalized
  score, LOW/MODERATE/HIGH/SEVERE, components, provenance, and limitations. Data quality, model
  confidence, and risk probability remain distinct.
- Uncertainty propagates aligned weighted scenarios and labels whether probability calibration
  exists. Explanations keep rainfall, flood/terrain, exposure, vulnerability, uncertainty, data
  quality, limitations, and versions separate and avoid causal claims.

No genuine physics targets currently exist; no real solver run, calibration, FNO training, or
measured speedup can be claimed.

## 29–30. Verification

Pre-change inherited regression: **71 passed, 31 warnings in 499.63 s**. The new focused
Phase 4E/5 suite passed after the final fixes: **25 passed in 12.40 s**. Full repository regression completed with
**273 passed, 1 failed, 47 warnings in 475.02 s**. The one failure,
`tests/test_phase3_acquisition.py::test_default_acquisition_is_bounded_dry_run`, is an
environment/data-state failure: the pre-existing raw directory is 0.923 GiB, above the legacy
0.800 GiB safety cap. This change does not touch acquisition code, data, or that cap. Scoped
Ruff F/I reports `All checks passed`; scoped Python `compileall` passed.

## 31. Future Colab Phase 4E commands

Run from `/content/JALAI/jalrakshak-ml-starter`. These paths are the declared Drive-backed
artifact locations; `test -f/-d` guards must pass before execution.

```bash
cd /content/JALAI/jalrakshak-ml-starter
test -d /content/drive/MyDrive/JALAI_DATA/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1
test -d /content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1
test -f /content/JALAI/jalrakshak-ml-starter/data/processed/static/elevation.npy
test -f /content/drive/MyDrive/JALAI_DATA/models/phase4e/normalization/phase4e_train_only_v1.json
COMMON=(--config configs/training/phase4e_final_v1.yaml --dataset-root /content/drive/MyDrive/JALAI_DATA/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1 --replay-root /content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1 --elevation /content/JALAI/jalrakshak-ml-starter/data/processed/static/elevation.npy --normalization /content/drive/MyDrive/JALAI_DATA/models/phase4e/normalization/phase4e_train_only_v1.json --replay-audit reports/phase4e_rich_replay_integrity_audit.json --channel-audit reports/phase4e_real_channels_audit.json --checkpoint-root /content/drive/MyDrive/JALAI_DATA/models/phase4e --execute)
```

1. Dataset/data-contract smoke:

```bash
python scripts/run_phase4e_final_training.py --mode data-smoke "${COMMON[@]}"
```

2. Genuine batch load: `python scripts/run_phase4e_final_training.py --mode batch-smoke "${COMMON[@]}"`.

3–5. GPU forward smoke:

```bash
python scripts/run_phase4e_final_training.py --mode model-smoke --model convlstm_v3 "${COMMON[@]}"
python scripts/run_phase4e_final_training.py --mode model-smoke --model unet_convgru_v1 "${COMMON[@]}"
python scripts/run_phase4e_final_training.py --mode model-smoke --model st_attention_nowcaster_v1 "${COMMON[@]}"
```

6–8. One-epoch debug:

```bash
for MODEL in convlstm_v3 unet_convgru_v1 st_attention_nowcaster_v1; do python scripts/run_phase4e_final_training.py --mode train --epochs 1 --model "$MODEL" --checkpoint-root /content/drive/MyDrive/JALAI_DATA/models/phase4e_debug "${COMMON[@]:0:14}" --execute; done
```

9–11. Full three-seed training, once per model:

```bash
for MODEL in convlstm_v3 unet_convgru_v1 st_attention_nowcaster_v1; do for SEED in 26071 26072 26073; do python scripts/run_phase4e_final_training.py --mode train --model "$MODEL" --seed "$SEED" "${COMMON[@]}"; done; done
```

12. Export validation predictions for Persistence, PySTEPS, and each deep checkpoint with
`scripts/export_phase4e_validation_predictions.py`, then compile them:

```bash
EVAL_COMMON=(--config configs/training/phase4e_final_v1.yaml --dataset-root /content/drive/MyDrive/JALAI_DATA/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1 --replay-root /content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1 --elevation /content/JALAI/jalrakshak-ml-starter/data/processed/static/elevation.npy --normalization /content/drive/MyDrive/JALAI_DATA/models/phase4e/normalization/phase4e_train_only_v1.json --replay-audit reports/phase4e_rich_replay_integrity_audit.json --channel-audit reports/phase4e_real_channels_audit.json)
python scripts/export_phase4e_validation_predictions.py --model persistence --output-root /content/drive/MyDrive/JALAI_DATA/reports/phase4e/persistence "${EVAL_COMMON[@]}"
python scripts/export_phase4e_validation_predictions.py --model pysteps --output-root /content/drive/MyDrive/JALAI_DATA/reports/phase4e/pysteps "${EVAL_COMMON[@]}"
for MODEL in convlstm_v3 unet_convgru_v1 st_attention_nowcaster_v1; do for SEED in 26071 26072 26073; do python scripts/export_phase4e_validation_predictions.py --model "$MODEL" --seed "$SEED" --checkpoint "/content/drive/MyDrive/JALAI_DATA/models/phase4e/full_inputs/$MODEL/seed_$SEED/best.pt" --output-root "/content/drive/MyDrive/JALAI_DATA/reports/phase4e/$MODEL/seed_$SEED" "${EVAL_COMMON[@]}"; done; done
python scripts/compile_phase4e_tournament.py --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/persistence/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/pysteps/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/convlstm_v3/seed_26071/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/convlstm_v3/seed_26072/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/convlstm_v3/seed_26073/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/unet_convgru_v1/seed_26071/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/unet_convgru_v1/seed_26072/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/unet_convgru_v1/seed_26073/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/st_attention_nowcaster_v1/seed_26071/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/st_attention_nowcaster_v1/seed_26072/manifest.json --manifest /content/drive/MyDrive/JALAI_DATA/reports/phase4e/st_attention_nowcaster_v1/seed_26073/manifest.json --output /content/drive/MyDrive/JALAI_DATA/reports/phase4e/final_validation_tournament.json
```

13. Event bootstrap is included by the compiler and records event unit/seed/iterations.

14. Run required ablations by adding `--ablation POLICY` to the training command for each of
the six names in `experiments.ABLATIONS`; export each validation result with
`--input-policy POLICY`.

15. Train controlled source-dropout variants by adding `--source-dropout SOURCE
--source-dropout-probability 0.1` for each of `observation`, `nwp`, and `terrain`; export
missing-source stress results using the corresponding `--input-policy` values.

16. Freeze only after all prerequisite evidence is materialized:

```bash
python scripts/freeze_phase4e_winner.py --selection /content/drive/MyDrive/JALAI_DATA/reports/phase4e/winner_selection.json --prerequisites /content/drive/MyDrive/JALAI_DATA/reports/phase4e/freeze_prerequisites.json --output /content/drive/MyDrive/JALAI_DATA/models/phase4e/winner_manifest.json --execute
```

Future locked test is a separate gated command only:

```bash
python scripts/run_phase4e_locked_test.py --winner-manifest /content/drive/MyDrive/JALAI_DATA/models/phase4e/winner_manifest.json --test-config configs/training/phase4e_locked_test_v1.yaml --execute
```

That test config intentionally does not exist in this preparation commit, so accidental test
execution fails closed.

## 32. Future Phase 5 dependency graph and gate commands

Each command validates its listed predecessor before a stage-specific engine may run. These
commands do not themselves fabricate or execute hydraulic science.

```bash
python scripts/check_phase5_stage.py --stage susceptibility-build --execute
python scripts/check_phase5_stage.py --stage susceptibility-audit --require reports/phase5_susceptibility_build.json --execute
python scripts/check_phase5_stage.py --stage physics-scenario-prepare --require reports/phase5_susceptibility_audit.json --execute
python scripts/check_phase5_stage.py --stage solver-environment-smoke --require data/processed/flood/physics_scenarios_v1.json --execute
python scripts/check_phase5_stage.py --stage one-genuine-physics-scenario --require reports/phase5_solver_environment_smoke.json --execute
python scripts/check_phase5_stage.py --stage physics-output-audit --require reports/phase5_one_physics_scenario.json --execute
python scripts/check_phase5_stage.py --stage multi-scenario-generation --require reports/phase5_physics_audit.json --execute
python scripts/check_phase5_stage.py --stage physics-dataset-freeze --require reports/phase5_multi_scenario_generation.json --execute
python scripts/check_phase5_stage.py --stage fno-normalization --require data/processed/flood/physics_dataset_v1.json --execute
python scripts/check_phase5_stage.py --stage fno-gpu-smoke --require models/flood/fno_train_only_normalization_v1.json --execute
python scripts/check_phase5_stage.py --stage fno-training --require reports/phase5_fno_gpu_smoke.json --execute
python scripts/check_phase5_stage.py --stage heldout-physics-comparison --require reports/phase5_fno_training.json --execute
python scripts/check_phase5_stage.py --stage exposure-build --require reports/phase5_susceptibility_audit.json --execute
python scripts/check_phase5_stage.py --stage vulnerability-build --require reports/phase5_exposure_build.json --execute
python scripts/check_phase5_stage.py --stage hev-risk --require reports/phase5_heldout_physics_comparison.json --require reports/phase5_exposure_build.json --require reports/phase5_vulnerability_build.json --execute
python scripts/check_phase5_stage.py --stage uncertainty-propagation --require reports/phase5_hev_risk.json --execute
python scripts/check_phase5_stage.py --stage explainability --require reports/phase5_uncertainty.json --execute
```

## 33–34. Changed files and local commit

The commit contains exactly these 31 source/config/test/report files:

- `configs/flood/phase5_foundation_v1.yaml`
- `configs/training/{phase4e_final_v1,convlstm_v3,unet_convgru_v1,st_attention_nowcaster_v1}.yaml`
- `reports/phase4e_phase5_foundation_report.md`
- `scripts/{check_phase5_stage,compile_phase4e_tournament,evaluate_phase4e_final_validation,export_phase4e_validation_predictions,freeze_phase4e_winner,run_phase4e_final_training,run_phase4e_locked_test}.py`
- `src/jalrakshak_ml/deep_nowcast/{convlstm_v3,experiments,final_contracts,final_dataset,final_evaluation,final_runner,final_tournament,phase4e_prepare,st_attention,unet_convgru}.py`
- `src/jalrakshak_ml/flood/{fno,physics,physics_dataset,susceptibility}.py`
- `src/jalrakshak_ml/risk/intelligence.py`
- `src/jalrakshak_ml/explain/risk_explanation.py`
- `tests/{test_phase4e_final_stack,test_phase5_foundation}.py`

The exact commit hash is reported alongside this committed report because a Git object cannot
embed its own hash. No raw/replay/Drive data, checkpoints, model outputs, secrets, or credentials
are included. `GIT_PUSHED=false`; `REMOTE_MODIFIED=false`.
