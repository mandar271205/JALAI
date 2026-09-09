# Phase 4E post-smoke implementation report

Date: 2026-09-09. This is an implementation and synthetic/unit-test handoff. No full GFS corpus download, replay generation, normalization fitting, training, validation tournament, model selection, or locked-test evaluation was executed.

## Outcome

The post-smoke non-test pipeline is prepared behind explicit execution and audit gates. The plan remains 15 events (12 train, 3 validation, 0 test), 255 issues, 30 cycles, and 225 minimal cycle+lead pairs. The real NOAA one-granule smoke result supplied in the handoff remains accepted as verified: 8 exact messages, 6,513,208 range-retrieved bytes, successful ecCodes parsing, signed winds, PRATE semantics, and canonical reprojection. Its Windows `C:\content\drive\...` mirror is **not** a Colab Drive mount.

## Production changes reviewed from the smoke

The smoke implementation added reusable rich-GFS support to `gfs_replay/grib.py`: NOAA `.idx` matching, explicit UGRD/VGRD/TMP/RH/PRES/CAPE/PWAT/PRATE identities, strict ambiguity/missing-field rejection, byte ranges, and a rich-field fetch helper. It also fixed a real cache filename defect (`cycle_dt` to the resolved `cycle_dt_val`). The standalone smoke script downloaded only the fixed non-test 2021-06-17 18Z f007 granule, decoded fields, checked physical units/ranges and signed winds, and performed canonical reprojection.

Post-review hardening removed the false Drive interpretation: Windows paths are local. `COLAB_DRIVE_PERSISTENCE_VERIFIED` can become true only when `google.colab` is loaded, `/content/drive/MyDrive` exists, the target is underneath that mount, and artifacts are reopened there. The smoke script now reports three distinct statuses: network smoke, local persistence, and genuine Colab Drive persistence. Production modules contain no fixed smoke cycle/lead or smoke output path.

## Downloader and raw corpus

`rich_download.py` implements the production path for the eight required fields. It uses `.idx` plus HTTP Range exclusively; a non-206 response is rejected and there is no full-GRIB fallback. It has separate connection/read timeouts, four bounded exponential-backoff attempts, deterministic `raw_gfs_cache/YYYYMMDD_HH/fXXX/` directories, atomic `.part` writes, envelope/declared-size/SHA-256 checks, ecCodes validation, resume/idempotency, per-field state, and an atomically updated per-granule manifest. A granule is complete only when all eight messages pass. Failed fields leave the granule incomplete and can be retried safely.

The top-level versioned manifest contains all 225 planned pairs, source and index URLs, expected variables, pair states, exact measured bytes, and complete/incomplete/missing/failed totals. Estimated transfer totals were removed from execution reporting. Smoke artifacts remain under `smoke/`; the production raw cache is separate.

NOAA inventory mapping is exact. PWAT accepts the two NOAA inventory spellings observed across products—`entire atmosphere` and `entire atmosphere (considered as a single layer)`—but rejects zero or multiple matches. Winds at 80/100 m, other pressure/CAPE/PWAT layers, and instantaneous PRATE cannot match.

## Temporal and spatial semantics

Formal PRATE metadata includes cycle, lead, raw start/end step, `avg` step type, raw statistical interval, reconstructed one-hour interval, native valid time, and units. PRATE is converted from kg m⁻² s⁻¹ through the existing physical reconstruction path. A 60-minute rate is allocated uniformly to overlapping 30-minute slots; the two slots preserve the same native-source provenance and are marked non-independent. No new temporal information is claimed.

Instantaneous fields retain both `aligned_target_time` and `source_native_valid_time`, plus offset/age, cycle, lead, assumed availability, and the exact availability basis `assumed_cycle_plus_6h_required_bundle_not_observed_publication`. Half-hour targets use the latest causal hourly instantaneous valid time. The availability time is an assumption, not an observed release timestamp.

The replay builder uses precipitation-specific non-negative processing and general `reproject_field()` for signed or non-rainfall variables. Wind speed and cyclic direction sine/cosine are derived only from genuine u/v fields. All outputs align to the unchanged Mumbai pilot grid, EPSG:32643 and 256×256; API CRS remains EPSG:4326. Native source resolution remains 0.25° (about 28 km). Reprojection is alignment, not super-resolution.

Rich issue storage retains source paths/hashes/parser state, availability masks, source/native/aligned times, and separate precipitation/meteorology arrays. The dataset contract remains `obs_history [4,1,H,W]`, `nwp_future [4,11,H,W]`, `static_features [1,H,W]`, and `target [4,1,H,W]`, with 128×128 training crops over the canonical 256×256 grid.

## Audit, normalization, tournament, ablations, and freeze gates

Three read-only auditors are prepared. The raw auditor reparses every message and checks all 225 pairs, hashes, GRIB framing, finite fraction, physical extrema, cycle/lead and PRATE timing. The replay auditor enforces 15/12/3/0 events and 255 issues, split isolation, source/aligned timestamps, cadence/resolution truthfulness, provenance and no later-cycle availability. The real-channel auditor separates implemented bindings from genuinely populated artifacts, verifies source files/hashes/parser state/masks, and always leaves radar/INSAT unavailable unless genuine data is supplied.

The final normalization fitter requires exactly the 12 authoritative train events and genuine replay provenance. It never opens validation or locked test and records count, finite count, mean, standard deviation, minimum and maximum separately for observation, NWP and static groups, plus versions, git SHA, channel order and source hashes. It was not run. Existing provisional hard-coded `MultiSourceStats` values remain legacy-only; the new validation runner refuses them as final normalization.

The validation-only GPU runner supports separated inputs, seeds 26071/26072/26073, AMP, atomic Drive-suitable checkpoints, resume, early stopping, best checkpoint, OOM micro-batch fallback, runtime, peak GPU memory, parameter count and hashes. Metrics cover MAE/RMSE/Bias/POD/FAR/CSI/F1 at +30/+60/+90/+120 and thresholds 0.1/1/5/10 where supported. Confidence intervals use event/event-block bootstrap, never independent pixels. Ablations A–D and the three source-dropout scenarios are declared in the execution plan.

The former `run_tournament()` entry point is disabled because it automatically proceeded from validation into locked-test evaluation. The new runner accepts train and validation loaders only. The winner freeze gate requires genuine full replay, both audits, final train-only normalization, multiseed training, validation tournament and ablations. It writes an immutable winner manifest but never runs locked test automatically.

## Validation performed

- Final unit/synthetic suite: **54 passed, 7 warnings in 24.62 s**.
- Tests cover real NOAA label mapping, wrong layers, ambiguity, exact ranges, no full fallback, partial/incomplete state, atomic resume, hashes/GRIB framing, PRATE 6–7 h timing, 60→30 provenance and mass consistency, source-vs-aligned timestamps, negative wind quadrants, cyclic wind encoding, Windows/Colab Drive distinction, zero locked-test events, 225 pairs, 255 issues, legacy tournament disablement and freeze gating.
- Ruff F/I checks and Python compilation passed for the new/changed implementation.
- Plan-only execution reproduced 15 events, 204 train issues, 51 validation issues, 0 test issues, 255 total issues, 30 cycles and 225 pairs. Zero network bytes were requested by this turn.

Warnings are upstream Rasterio affine deprecation notices; no assertion failed.

## Remaining genuine Colab execution sequence

1. Mount Google Drive and rerun the one-granule smoke to independently verify reopen-from-Drive persistence.
2. Run `prepare_gfs_rich_replay.py --download` with the Phase 4E Drive root. This is the first action that starts the 225-pair acquisition.
3. Run `audit_phase4e_rich_gfs_download.py`; require 225 complete pairs and zero missing/incomplete/failed pairs.
4. Run `build_phase4e_rich_replay.py --execute` against the audited raw cache.
5. Run the replay-integrity and real-channel auditors; require both to pass.
6. Run `fit_phase4e_normalization.py --execute` on the 12 train events only.
7. Instantiate the validation-only runner, train all three seeds with Drive checkpoints, then run validation metrics, event-block confidence intervals, ablations and source-dropout checks.
8. Freeze one winner only if every prerequisite is satisfied. Do not automatically evaluate the locked test split.

## Files changed

Created for post-smoke hardening:

- `src/jalrakshak_ml/gfs_replay/rich_download.py`
- `src/jalrakshak_ml/gfs_replay/phase4e_audit.py`
- `src/jalrakshak_ml/deep_nowcast/phase4e_prepare.py`
- `src/jalrakshak_ml/deep_nowcast/phase4e_runner.py`
- `scripts/audit_phase4e_rich_gfs_download.py`
- `scripts/audit_phase4e_rich_replay.py`
- `scripts/audit_phase4e_real_channels.py`
- `scripts/build_phase4e_rich_replay.py`
- `scripts/fit_phase4e_normalization.py`
- `scripts/run_phase4e_validation_tournament.py`
- `scripts/freeze_phase4e_winner.py`
- `tests/test_phase4e_post_smoke.py`
- `reports/phase4e_rich_gfs_download_audit.json` (explicit `NOT_RUN` state)
- `reports/phase4e_rich_replay_integrity_audit.json` (explicit `NOT_RUN` state)
- `reports/phase4e_real_channels_audit.json` (explicit `NOT_RUN` state)
- `reports/phase4e_validation_tournament_plan.json`
- this implementation report

Reviewed/refactored or extended:

- `scripts/smoke_test_rich_gfs_real_download.py`
- `src/jalrakshak_ml/gfs_replay/grib.py`
- `src/jalrakshak_ml/gfs_replay/rich_pipeline.py`
- `scripts/prepare_gfs_rich_replay.py`
- `src/jalrakshak_ml/deep_nowcast/tournament.py`
- `configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml`
- `reports/phase4e_rich_gfs_replay_plan.json`

## Scientific concern

The largest remaining concern is provenance, not code: the six-hour required-bundle availability time is conservative but assumed. Genuine replay can prove the selected cycle predates issue time under that policy; it cannot prove the exact historical NOAA publication instant without an external publication log. The second concern is the legacy provisional normalization path. It is explicitly rejected by the new runner, but callers outside the new runner must not mistake it for fitted Phase 4E statistics.

## Status

```text
PHASE_4E_POST_SMOKE_IMPLEMENTATION_READY=true
NOAA_REAL_SMOKE_ALREADY_VERIFIED=true
COLAB_DRIVE_REAL_PERSISTENCE_VERIFIED=false
FULL_225_DOWNLOAD_STARTED=false
LOCKED_TEST_TOUCHED=false
NORMALIZATION_FITTED=false
TRAINING_STARTED=false
MODEL_SELECTION_FROZEN=false
LOCKED_TEST_ALLOWED_FOR_SINGLE_FINAL_EVALUATION=false
```
