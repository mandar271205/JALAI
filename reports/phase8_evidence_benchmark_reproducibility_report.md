# Phase 8 — Evidence, Verification, Benchmark & Reproducibility Hardening

Generated: 2026-09-09 (Asia/Kolkata)
Scope: code, contracts, tests, metadata reports, and fixture-only integration. Phase 4E training, replay, normalization, checkpoint selection, and the locked test were excluded.

## 1. Files inspected

The audit covered the repository status/history and the Phase 4E, Phase 5, and Phase 7 implementation surfaces, including:

- `src/jalrakshak_ml/core/claim_gates.py`
- `src/jalrakshak_ml/benchmark/final_harness.py`
- `src/jalrakshak_ml/citizen/verification.py`
- `src/jalrakshak_ml/explain/risk_explanation.py`
- flood forcing, evidence, exposure, vulnerability, physics orchestration, and FNO modules
- GPM/GFS meteorological contracts and adapters
- serving schemas/service/application code
- Phase 4E final-stack, replay-hardening, and training contracts
- Phase 5 and Phase 7 tests and all Phase 7 evidence/readiness reports
- the genuine-data inventory and source provenance manifests under `reports/`
- Phase 4E configuration was read only; no training, replay, normalization, split, or checkpoint file was modified.

The required commits were present before implementation: `fa47dc7`, `71155a3`, `0de3b81`, and `ea498af`.

## 2. Files created

- Evidence and catalog: `src/jalrakshak_ml/evidence/{contracts,catalog}.py`
- Citizen V2: `src/jalrakshak_ml/citizen/{verification_v2,dataset,baseline}.py`
- Risk explanation V2: `src/jalrakshak_ml/explain/risk_explanation_v2.py`
- Phase 8 research package: benchmark, claims, confidence, decision/fallback, freshness, integration, registry, reproducibility, run manifest, serving adapters, source registry, statistics, status, and table exporters
- Four versioned YAML configurations under `configs/evidence`, `configs/benchmark`, `configs/citizen`, and `configs/reproducibility`
- Twelve requested CLI entry points under `scripts/`
- `tests/test_phase8_evidence_benchmark.py`
- Generated metadata: this report, the offline dry-run manifest, fail-closed benchmark skeleton, project status, and source capability matrix

No existing nowcast, fusion, Phase 4E, physics, FNO, or backend-serving implementation was modified.

## 3. Implemented architecture

The implementation adds:

1. Strict evidence records with source, time/space, units, quality, confidence, provenance, checksum, caveats, and quantity typing. `SUSCEPTIBILITY_ONLY` is rejected as depth or observed extent.
2. An evidence-gated Mumbai event state machine. Candidate windows cannot claim severity; verified events require rainfall and flood evidence; benchmark eligibility additionally requires exposure and vulnerability snapshots.
3. Eight-layer rules-only citizen corroboration with duplicate/spam handling, optional image/ML interfaces, and no `verified flood truth` output.
4. A labeled citizen dataset builder that requires label provenance, rejects pseudo-labels, splits by event, blocks duplicate-group leakage, excludes `UNKNOWN`, hashes inputs, and writes immutable manifests.
5. An optional TF-IDF + structured logistic-regression baseline with precision/recall/F1/confusion matrix and binary PR-AUC/Brier support. It is gated off because no genuine labels were found locally.
6. A hash-addressed model/data/evidence lifecycle registry. Unfinished Phase 4E artifacts cannot become `FROZEN`, and frozen states require an immutable freeze-manifest hash.
7. Executable scientific claim decisions with required/present evidence, blockers, safe phrasing, forbidden phrasing, and strict nonzero CLI exit behavior.
8. A five-dimension benchmark framework in which unavailable reference data yields `NOT_EVALUABLE`, never zero.
9. Paired event/scenario bootstrap statistics using independent blocks rather than pixels.
10. Atomic immutable run manifests with git/config/source/model/normalization references, splits, device/CUDA state, seeds, inputs, outputs, metrics, claim gates, and locked-test protection.
11. A metadata-only reproducibility bundle builder with repository-bound paths, suffix/size allowlists, and raw/secret/checkpoint exclusions.
12. Source capability and freshness engines that distinguish adapter existence, actual population, and observed versus assumed latency.
13. Separate confidence components and an explicitly heuristic combined summary.
14. Risk explanation V2, advisory-only recommendations, endpoint serializers with lifecycle states, deterministic fallbacks, status reporting, and research table exporters.

## 4. Scientific assumptions and safeguards

- GPM IMERG Final is satellite precipitation and historical reference data, not radar and not a real-time source.
- GFS is native coarse NWP guidance; canonical-grid resampling does not create physical spatial resolution.
- Derived cadence is not labeled as a new independent observation.
- Susceptibility is dimensionless relative screening, not water depth or observed inundation.
- Citizen rainfall/model consistency is contextual support, not ground truth or a calibrated probability.
- OSM waterways are incomplete for municipal drainage and cannot establish SWMM readiness.
- Proxy vulnerability is neither calibrated vulnerability nor a causal social conclusion.
- No unexecuted solver output, synthetic depth, or unavailable FNO target is treated as physics truth.

## 5. Genuine data available

Repository evidence confirms a genuine GPM IMERG V07 historical corpus, populated NOAA GFS replay artifacts, Copernicus GLO-30 DEM and derived terrain rasters, OSM roads/waterways/railways/facilities, and a dimensionless susceptibility grid. Existing reports also document the canonical 256×256 Mumbai grid and source hashes.

## 6. Missing genuine data

No local genuine citizen labels, observed/calibrated flood depth, empirical flood validation extent, population raster, building exposure layer, municipal closed-drainage network, or calibrated vulnerability survey is available. LISFLOOD-FP inputs exist, but the solver is unavailable and no real simulation has executed. Consequently, genuine FNO targets, FNO training, calibrated depth, and depth validation remain blocked.

## 7. Tests and quality checks

- Pre-change Phase 5/7 baseline: **55 passed, 2 warnings**.
- Final Phase 8 focused suite: **50 passed in 31.72s**.
- Phase 8 + Phase 5/7 scientific regression before the final three Phase 8 refinements: **89 passed, 2 warnings**; the final Phase 8 rerun was green.
- Selected Phase 4E isolation/locked-test contracts were also included in the full suite and passed.
- Full repository pytest: **350 passed, 1 failed, 49 warnings in 753.46s**. The sole failure was the pre-existing `tests/test_phase3_acquisition.py::test_default_acquisition_is_bounded_dry_run`: genuine raw storage is 0.923 GiB, above the configured 0.800 GiB safety cap. The acquisition guard was deliberately preserved; no raw data or Phase 3/4E configuration was changed.
- Scoped Ruff: **all checks passed**.
- Compileall: **passed**.
- All 12 Phase 8 CLIs are covered by `--help` smoke tests.

Tests cover evidence type safety, susceptibility/depth separation, event transitions, citizen duplicate leakage, unknown/pseudo-label exclusion, lifecycle freeze protection, claim gates, freshness and latency basis, confidence separation, risk caveats, fallbacks, `NOT_EVALUABLE`, block bootstrap, atomic manifests, hashing, metadata bundle exclusions, serving safety, and the fixture-only dry run.

## 8. Benchmark readiness

The orchestration and metric contracts are ready. The generated skeleton contains 33 metric slots across rainfall, flood physics, FNO, risk, and citizen verification. Every slot without a genuine evaluation/reference is `NOT_EVALUABLE` with a reason. This task did not run a final model benchmark or access locked-test observations.

## 9. Citizen verification readiness

Citizen Verification V2 rules-only corroboration is executable. Future labeled-dataset and baseline-training paths are executable and leakage-gated. No genuine labels were discovered, so training was not started and real citizen ML remains unavailable.

## 10. Source capability status

GPM Final, NOAA GFS, Copernicus DEM, and OSM are integrated and populated for their declared research roles. GPM NRT is represented as a future capability but is not configured, integrated, or locally populated. IMD DWR and MOSDAC INSAT are not integrated or populated. Population and empirical flood-validation sources are missing. GPM Final's nominal latency and GFS publication latency remain explicitly `ASSUMED`; source observation/issue time is not conflated with observed publication availability.

## 11. Claim-gate status

With current evidence, `FLOOD_SUSCEPTIBILITY` is allowed using the safe phrase “Relative flood susceptibility is high.” Claims for flood depth, verified citizen truth, real-time radar nowcast, and calibrated probability are blocked. The strict CLI exits nonzero when a requested blocked claim is evaluated.

## 12. Integration dry-run result

`reports/phase8_offline_dryrun_manifest.json` was created atomically from explicit fixture metadata. It used no locked-test data, emitted only `SUSCEPTIBILITY_ONLY`, marked depth and all unavailable flood/FNO metrics `NOT_EVALUABLE`, used rules-only citizen corroboration, selected a nowcast-only/no-radar fallback, and produced an advisory `VERIFY_LOCALLY` recommendation requiring human review.

## 13. Limitations

The evidence registry and event catalog are validated frameworks, not claims that a fully verified historical flood catalog is populated. The benchmark skeleton is readiness infrastructure, not a completed final benchmark. The confidence summary is heuristic. The citizen image layer validates metadata presence only; no image-content model is active. The dry run verifies integration behavior, not predictive skill.

## 14. Next remaining work

1. Ingest independently sourced, licensed, checksum-verified flood extent/depth and official incident evidence.
2. Obtain municipal drainage and calibration inputs, execute a real hydraulic solver, and audit mass balance.
3. Build FNO targets only from accepted genuine solver runs, then train/evaluate with event/scenario separation.
4. Collect human-labeled citizen reports with explicit provenance and duplicate-group identity before enabling citizen ML.
5. Populate exposure/vulnerability evidence and calibrate risk against independent event labels.
6. After authorized Phase 4E completion, ingest frozen artifacts into the lifecycle registry and run the final locked benchmark exactly once under its established controls.

## 15. Git state

Pre-implementation HEAD was `fa47dc792db1d6296d4d530058cc4706712e72d6` on `main`, and the worktree was clean. Only the Phase 8 code/config/test/metadata paths listed above were added. The required final local commit subject is:

`feat(research): harden evidence verification benchmarking and reproducibility`

No push or remote modification is authorized or performed.

Pre-commit `git log --oneline -10`:

```text
fa47dc7 feat(geo): prepare genuine flood physics and risk data inputs
71155a3 feat(ml): implement flood intelligence and risk research pipeline
a7aa17d docs: add authoritative backend-ML integration audit report
0de3b81 feat(ml): harden Phase 4E tournament and scaffold flood intelligence research stack
ea498af feat(phase4e): harden post-replay integrity audit, real-channel audit, and train-only normalization
4c2110d feat(monorepo): add full JalRakshak backend service to backend/
33ab266 feat(serving): implement ML serving microservice and complete PRATE verification suite
e01b38f fix(phase4e): correct PRATE mean-rate semantics in rich replay pipeline
48c98d9 feat(phase4e): add resumable rich-gfs replay and validation gates
fa983fa feat(phase4e): implement rich-gfs pre-download audit fixes and decoupled conditioning
```

The pre-commit status contained only the Phase 8 untracked paths enumerated in Section 2; no tracked Phase 4E, data, normalization, or checkpoint path was modified.

## Machine-readable status

```text
PHASE_8_IMPLEMENTATION_COMPLETE=true
HISTORICAL_EVIDENCE_REGISTRY_READY=true
FLOOD_EVENT_CATALOG_READY=true
CITIZEN_VERIFICATION_V2_READY=true
CITIZEN_DATASET_BUILDER_READY=true
CITIZEN_GENUINE_LABELS_AVAILABLE=false
CITIZEN_ML_TRAINING_STARTED=false
CITIZEN_REAL_ML_AVAILABLE=false
MODEL_DATA_EVIDENCE_REGISTRY_READY=true
SCIENTIFIC_CLAIM_GATE_READY=true
FINAL_BENCHMARK_FRAMEWORK_READY=true
EVENT_BLOCK_BOOTSTRAP_READY=true
RUN_MANIFEST_READY=true
REPRODUCIBILITY_BUNDLE_READY=true
SOURCE_CAPABILITY_REGISTRY_READY=true
DATA_FRESHNESS_ENGINE_READY=true
COMPOSITE_CONFIDENCE_CONTRACT_READY=true
RISK_EXPLANATION_V2_READY=true
DECISION_SUPPORT_CONTRACT_READY=true
SERVING_ADAPTERS_READY=true
FAILURE_FALLBACK_MATRIX_READY=true
OFFLINE_INTEGRATION_DRYRUN_READY=true
RESEARCH_TABLE_EXPORT_READY=true
REAL_PHYSICS_SIMULATION_EXECUTED=false
GENUINE_FNO_TARGETS_AVAILABLE=false
FNO_TRAINING_STARTED=false
CALIBRATED_FLOOD_DEPTH_AVAILABLE=false
LOCKED_TEST_TOUCHED=false
PHASE_4E_TRAINING_STARTED=false
PHASE_4E_REPLAY_MODIFIED=false
NORMALIZATION_MODIFIED=false
FABRICATED_DEPTH_USED=false
FAKE_PHYSICS_TRUTH_USED=false
FAKE_CITIZEN_LABELS_USED=false
RAW_DATA_COMMITTED=false
MODEL_CHECKPOINT_COMMITTED=false
SECRETS_COMMITTED=false
LOCAL_COMMIT_CREATED=true
GIT_PUSHED=false
REMOTE_MODIFIED=false
```
