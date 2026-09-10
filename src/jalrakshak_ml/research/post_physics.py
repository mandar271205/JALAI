"""Consolidated local research auditor. No rainfall training, data loading or downloads."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio

from jalrakshak_ml.citizen.metadata_verifier import MetadataVerifier
from jalrakshak_ml.flood.forensic import audit_phase10, read_json, safe_path, sha
from jalrakshak_ml.flood.smoke_evaluation import evaluate_checkpoint
from jalrakshak_ml.flood.verified_dataset import validate_sample
from jalrakshak_ml.risk.evidence_layers import build_exposure, build_vulnerability
from jalrakshak_ml.risk.scenario_risk import evaluate_risk, explain_cell, scenario_uncertainty
from jalrakshak_ml.serving.flood_evidence_contracts import FloodEvidenceArtifact


def write_report(out: Path, name: str, data: dict):
    out.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, allow_nan=False, default=lambda v: v.item() if isinstance(v, np.generic) else str(v))
    (out / f'{name}.json').write_text(content + '\n', encoding='utf-8')
    (out / f'{name}.md').write_text(f'# {name.replace("_", " ")}\n\n```json\n{content}\n```\n', encoding='utf-8')


def claim_gates(*, forensic: dict, fno: dict, exposure: dict, vulnerability: dict,
                 risk_ready: bool, solver: dict) -> dict:
    genuine = forensic.get('genuine_solver_runs', 0) > 0
    corrected_ready = forensic.get('corrected_corpus', {}).get('verified', False)
    corrected_out = bool(forensic.get('corrected_corpus', {}).get('runs') or forensic.get('corrected_diagnostic'))
    return {'PHYSICS_DOMAIN_READY': corrected_ready, 'RAINFALL_FORCING_READY': corrected_ready,
            'LISFLOOD_EXECUTABLE': solver.get('verified', False), 'LISFLOOD_SMOKE_EXECUTED': genuine,
            'GENUINE_SOLVER_OUTPUT_AVAILABLE': genuine,
            'CORRECTED_SOLVER_OUTPUT_AVAILABLE': corrected_out,
            'CORRECTED_SOLVER_GRID_VALID': corrected_ready,
            'OLD_PHASE10_TRAINING_TARGETS_VERIFIED': False,
            'PHYSICS_DATASET_READY': corrected_ready,
            'FNO_READY_FOR_SMOKE': corrected_ready, 'FNO_ACTUALLY_TRAINED': fno.get('checkpoint_epoch', 0) > 0,
            'FNO_SCIENTIFICALLY_VALIDATED': False, 'FNO_CALIBRATED': False, 'FNO_OPERATIONAL': False,
            'EXPOSURE_READY': exposure.get('status') == 'PARTIAL_MAPPED_ASSETS',
            'VULNERABILITY_READY': vulnerability.get('status') == 'GEOPHYSICAL_PROXY_ONLY',
            'RISK_ENGINE_READY': risk_ready, 'UNCERTAINTY_READY': risk_ready,
            'EXPLAINABILITY_READY': risk_ready, 'CITIZEN_VERIFICATION_READY': True,
            'CITIZEN_ML_MODEL_AVAILABLE': False, 'RAIN_FORECAST_WINNER_FROZEN': False}


def probe_solver() -> dict:
    command = ['wsl', '-d', 'Ubuntu', '--', '/usr/local/bin/lisflood', '-version']
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=25, check=False)
        verified = result.returncode == 0 and 'LISFLOOD-FP version 8.0.3' in result.stdout
        checksum = subprocess.run(['wsl', '-d', 'Ubuntu', '--', 'sha256sum', '/usr/local/bin/lisflood'],
                                  capture_output=True, text=True, timeout=15, check=False)
        digest = checksum.stdout.split()[0] if checksum.returncode == 0 else None
        return {'verified': verified, 'command': command, 'exit_code': result.returncode,
                'stdout': result.stdout.strip(), 'binary_sha256': digest}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'verified': False, 'command': command, 'blocker': str(exc)}


def protected_hashes(root: Path) -> dict:
    paths = subprocess.run(['git', 'ls-files', 'src/jalrakshak_ml/deep_nowcast',
                            'configs/training', 'colab'], cwd=root, capture_output=True,
                           text=True, check=True).stdout.splitlines()
    return {p: sha(root / p) for p in paths}


def run_audit(root: Path, out: Path, *, audit_only: bool, benchmark: bool, strict: bool) -> int:
    root = Path(root).resolve()
    out = Path(out).resolve()
    protected = protected_hashes(root)
    started = time.perf_counter()
    timing, failures = {}, []
    solver = probe_solver()
    forensic = audit_phase10(root)
    diagnostic_path = safe_path(root, 'data/processed/flood/physics_outputs/phase11_back_loaded_v2/diagnostic_manifest.json')
    if diagnostic_path.is_file():
        diagnostic = read_json(diagnostic_path)
        diagnostic['manifest_sha256'] = sha(diagnostic_path)
        forensic['corrected_diagnostic'] = diagnostic
    forensic['solver_binary_evidence'] = solver
    corrected_path = safe_path(root, 'data/processed/flood/physics_outputs/phase11_corpus_v1/corpus_report.json')
    corrected = {'verified': False, 'status': 'UNAVAILABLE'}
    if corrected_path.is_file():
        try:
            corrected = read_json(corrected_path)
            samples = read_json(safe_path(root, corrected['manifest_path']))
            for record in samples['records']:
                validate_sample(root, record)
            if sha(safe_path(root, corrected['manifest_path'])) != corrected['manifest_sha256']:
                raise ValueError('Corrected sample manifest hash mismatch')
            dataset_dir = safe_path(root, corrected['dataset_dir'])
            norm = read_json(dataset_dir / 'fno_train_only_normalization.json')
            train_ids = [r['scenario_id'] for r in samples['records'] if r['split'] == 'train']
            val_ids = [r['scenario_id'] for r in samples['records'] if r['split'] == 'validation']
            if set(train_ids) & set(val_ids) or norm['fitted_scenario_ids'] != train_ids:
                raise ValueError('Corrected corpus split/normalization isolation failure')
            train_x = np.load(dataset_dir / 'train_inputs.npy', allow_pickle=False, mmap_mode='r')
            if not all(np.isclose(train_x[:, i].mean(), norm['input_statistics'][ch]['mean'], rtol=1e-5)
                       for i, ch in enumerate(norm['channel_order'])):
                raise ValueError('Corrected train normalization mean mismatch')
            corrected.update(verified=True, normalization_train_only_verified=True,
                             training_eligibility='SMOKE_ONLY_ONE_60MIN_TARGET; independent of legacy checkpoint')
        except (OSError, KeyError, ValueError) as exc:
            corrected.update(verified=False, error=str(exc))
            failures.append(str(exc))
    forensic['corrected_corpus'] = corrected
    write_report(out, 'phase11_corrected_physics_corpus', corrected)
    forensic['manual_reference'] = 'https://www.bristol.ac.uk/media-library/sites/geography/migrated/documents/lisflood-manual-v5.9.6.pdf'
    write_report(out, 'phase11_flood_forensic_audit', forensic)
    try:
        start = time.perf_counter()
        fno = evaluate_checkpoint(root, repeats=3 if benchmark else 1)
        timing['fno_evaluation_seconds'] = time.perf_counter() - start
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        fno = {'status': 'BLOCKED', 'reason': str(exc), 'FNO_SCIENTIFICALLY_VALIDATED': False,
               'FNO_CALIBRATED': False, 'FNO_OPERATIONAL': False}
        failures.append(str(exc))
    write_report(out, 'fno_smoke_evaluation', fno)
    exposure, vulnerability, risk_report, uncertainty_report, explanation = {}, {}, {}, {}, {}
    risk_ready = False
    serving = {'status': 'CONTRACT_AVAILABLE_NO_LIVE_ARTIFACT'}
    try:
        start = time.perf_counter()
        exposure, e, e_mask, profile = build_exposure(root)
        timing['exposure_build_seconds'] = time.perf_counter() - start
        start = time.perf_counter()
        vulnerability, v, v_mask = build_vulnerability(root, profile)
        timing['vulnerability_build_seconds'] = time.perf_counter() - start
        hazard_path = safe_path(root, 'data/processed/flood/susceptibility_v1.tif')
        with rasterio.open(hazard_path) as src:
            if src.crs != profile['crs'] or src.transform != profile['transform'] or src.shape != e.shape:
                raise ValueError('Susceptibility/canonical grid mismatch')
            h = src.read(1)
            mask = e_mask & v_mask & src.read_masks(1).astype(bool) & np.isfinite(h)
        start = time.perf_counter()
        risk = evaluate_risk(h, e, v, mask, hazard_type='susceptibility', units='relative_index',
                             hazard_scale=1., provenance={'hazard': {'path': str(hazard_path.relative_to(root)), 'sha256': sha(hazard_path)},
                             'exposure': exposure['version'], 'vulnerability': vulnerability['version']},
                             quality=float(mask.mean()), confidence=None)
        timing['risk_engine_seconds'] = time.perf_counter() - start
        risk_report = {'status': 'EXECUTED_RELATIVE_SCREENING', 'version': risk['version'],
                       'hazard_type': risk['hazard_type'], 'valid_cells': int(mask.sum()),
                       'quality': risk['quality'], 'confidence': None,
                       'mean_risk': float(risk['risk_score'][mask].mean()),
                       'maximum_risk': float(risk['risk_score'][mask].max()),
                       'classes': {k: int((risk['risk_class'] == k).sum()) for k in ('LOW', 'MODERATE', 'HIGH', 'SEVERE', 'NODATA')},
                       'provenance': risk['provenance'], 'calibrated_damage': False,
                       'interpretation': 'conditional relative risk among mapped assets; unknown unmapped exposure'}
        start = time.perf_counter()
        scenarios = [evaluate_risk(h, e, np.clip(v * scale, 0, 1), mask,
                                  hazard_type='susceptibility', units='relative_index', hazard_scale=1.,
                                  provenance=risk['provenance'], quality=risk['quality'], confidence=None)
                     for scale in (.8, 1., 1.2)]
        uncertainty = scenario_uncertainty(scenarios, np.asarray([1 / 3] * 3))
        timing['uncertainty_seconds'] = time.perf_counter() - start
        uncertainty_report = {'status': 'EXECUTED_SENSITIVITY_SCENARIOS', 'scenario_count': 3,
                              'scenario_definition': 'vulnerability scaling 0.8, 1.0, 1.2; equal weights, expert sensitivity only',
                              'rainfall_forecast_uncertainty_available': False, 'calibrated_probability': False,
                              'confidence': None, 'mean_spread': float(uncertainty['spread'][mask].mean()),
                              'quantile_method': 'weighted empirical CDF; not confidence intervals',
                              'missing_source_uncertainty': uncertainty['missing_source_uncertainty']}
        row, col = np.unravel_index(np.nanargmax(risk['risk_score']), h.shape)
        start = time.perf_counter()
        explanation = explain_cell(risk, int(row), int(col))
        timing['explainability_seconds'] = time.perf_counter() - start
        explanation['cell'] = [int(row), int(col)]
        if not audit_only:
            arrays = safe_path(root, 'data/processed/flood/physics_outputs/phase11_products')
            arrays.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(arrays / 'risk_layers.npz', exposure=e, vulnerability=v,
                                risk=risk['risk_score'], valid_mask=mask, expected_risk=uncertainty['expected_risk'],
                                lower=uncertainty['lower'], median=uncertainty['median'], upper=uncertainty['upper'])
        risk_ready = True
        serving = FloodEvidenceArtifact(
            run_id='phase11-relative-screening', generated_at=datetime.now(UTC),
            model_version='relative_susceptibility_v1', data_version='local_static_snapshot',
            hazard_type='susceptibility', units='relative_index', raster_crs=str(profile['crs']),
            raster_transform=tuple(profile['transform'])[:6], raster_shape=h.shape,
            artifact_path=str(hazard_path.relative_to(root)), artifact_sha256=sha(hazard_path),
            provenance=risk['provenance'], uncertainty={'calibrated': False, 'coverage_unknown': True},
            quality=risk['quality'], confidence=None, status='experimental').model_dump(mode='json')
    except (OSError, ValueError, KeyError) as exc:
        failures.append(str(exc))
        risk_report = {'status': 'BLOCKED', 'reason': str(exc)}
    for name, data in [('phase11_exposure_evidence', exposure), ('phase11_vulnerability_evidence', vulnerability),
                       ('phase11_risk_evidence', risk_report), ('phase11_uncertainty_evidence', uncertainty_report),
                       ('phase11_explainability_evidence', explanation)]:
        write_report(out, name, data)
    citizen = {'version': MetadataVerifier.version, 'status': 'RULES_IMPLEMENTED_REAL_REPORTS_UNAVAILABLE',
               'CITIZEN_VERIFICATION_RULE_BASED': True, 'CITIZEN_ML_MODEL_AVAILABLE': False,
               'real_report_accuracy_benchmark': None, 'manual_review_required': True,
               'interface': 'citizen.metadata_verifier.ReportVerifier',
               'rules': ['explicit-clock timestamp', 'Mumbai bounds', 'same-event spatial/time clustering',
                         'text/media-hash duplicates', 'rain/hazard consistency', 'media type'],
               'source_history_available': False}
    write_report(out, 'phase11_citizen_verification_evidence', citizen)
    write_report(out, 'phase11_serving_contract_evidence', {'artifact': serving,
                 'http_routes_modified': False, 'future_rainfall_model_activated': False,
                 'contract': 'serving.flood_evidence_contracts.FloodEvidenceArtifact'})
    gates = claim_gates(forensic=forensic, fno=fno, exposure=exposure, vulnerability=vulnerability,
                        risk_ready=risk_ready, solver=solver)
    claims = {
        'JalRakshak executes genuine LISFLOOD-FP.': 'SUPPORTED' if gates['GENUINE_SOLVER_OUTPUT_AVAILABLE'] else 'NOT_YET_SUPPORTED',
        'Corrected LISFLOOD diagnostic exists.': 'SUPPORTED' if gates['CORRECTED_SOLVER_OUTPUT_AVAILABLE'] else 'NOT_YET_SUPPORTED',
        'Old Phase 10 six-scenario corpus is valid for FNO training.': 'NOT_YET_SUPPORTED',
        'Corrected physics corpus is valid.': 'SUPPORTED' if gates['PHYSICS_DATASET_READY'] else 'NOT_YET_SUPPORTED',
        'FloodFNO historical smoke training occurred.': 'SUPPORTED' if gates['FNO_ACTUALLY_TRAINED'] else 'NOT_YET_SUPPORTED',
        'FloodFNO is scientifically validated.': 'NOT_YET_SUPPORTED',
        'FloodFNO is calibrated.': 'NOT_YET_SUPPORTED',
        'FloodFNO is operational.': 'NOT_YET_SUPPORTED',
        'Flood depth is calibrated to observed Mumbai truth.': 'NOT_YET_SUPPORTED',
        'Risk decomposition is executable.': 'SUPPORTED' if risk_ready else 'NOT_YET_SUPPORTED',
        'Rainfall final winner is frozen.': 'NOT_YET_SUPPORTED',
        'Radar/INSAT are operationally populated.': 'NOT_YET_SUPPORTED',
        'Citizen ML verifier exists.': 'NOT_YET_SUPPORTED',
        'Runs genuine LISFLOOD-FP simulations': 'SUPPORTED' if gates['GENUINE_SOLVER_OUTPUT_AVAILABLE'] else 'NOT_YET_SUPPORTED',
        'Solver-generated flood-depth arrays exist': 'SUPPORTED',
        'Legacy solver arrays correctly located on Mumbai grid': 'NOT_YET_SUPPORTED',
        'Exposure complete for Mumbai': 'PARTIALLY_SUPPORTED',
        'Social vulnerability available': 'NOT_YET_SUPPORTED',
        'Citizen flood reports verified by trained ML': 'NOT_YET_SUPPORTED'}
    blockers = ['Legacy corpus quarantined: grid distortion, forcing timing defects, repeated peak targets.',
                'Corrected corpus is only a small smoke corpus with one 60-minute target; expand events/time horizons before serious FNO training.',
                'Full Phase 4E Colab tournament and explicit winner freeze remain external.',
                'Observed flood-depth truth, calibrated hydraulics and social vulnerability missing.',
                'Population/buildings/power coverage incomplete; source dates do not establish historical exposure.',
                'No real labeled citizen corpus or calibrated uncertainty evidence.'] + failures
    write_report(out, 'final_ml_claim_matrix', {'claims': claims, 'gates': gates, 'blockers': blockers})
    registry = {'version': 'phase11_model_data_evidence_registry_v1', 'records': [
        {'id': 'future_rainfall_winner', 'status': 'unavailable', 'frozen': False, 'checkpoint_opened': False},
        {'id': 'lisflood_8.0.3', 'status': 'experimental', 'evidence': solver},
        {'id': 'phase10_physics_dataset', 'status': 'smoke_only', 'training_eligible': False},
        {'id': 'phase11_corrected_physics_dataset', 'status': 'smoke_only',
         'training_eligible_for_smoke': corrected.get('verified', False),
         'dataset_version': corrected.get('dataset_version'), 'sha256': corrected.get('manifest_sha256')},
        {'id': 'flood_fno_smoke', 'status': 'smoke_only', 'validated': False, 'operational': False,
         'sha256': fno.get('checkpoint_sha256')},
        *[{'id': key, 'status': 'experimental'} for key in ('susceptibility', 'exposure_v1',
          'geophysical_vulnerability_v1', 'hev_risk_v1', 'explainability_v1', MetadataVerifier.version)]]}
    write_report(out, 'phase11_evidence_registry', registry)
    benchmark_report = {'version': 'flood_intelligence_benchmark_v1', 'timings': timing,
                        'solver_runtime_seconds': [r.get('runtime_seconds') for r in forensic['runs']],
                        'solver_process_success_rate': sum(r['solver_success'] for r in forensic['runs']) / max(1, len(forensic['runs'])),
                        'canonical_training_eligible_runs': forensic['canonical_training_eligible'],
                        'corrected_solver_runtime_seconds': [r.get('runtime_seconds') for r in corrected.get('runs', [])],
                        'corrected_smoke_dataset_verified': corrected.get('verified', False),
                        'depth_wet_support': {r['scenario_id']: r.get('wet_cells') for r in forensic['runs']},
                        'fno_latency': fno.get('latency'), 'fno_macro_metrics': fno.get('macro'),
                        'susceptibility_generation_runtime': None, 'rainfall_tournament_benchmarked': False,
                        'audit_wall_seconds': time.perf_counter() - started,
                        'timing_basis': 'measured local CPU wall clock; solver historical per-run records'}
    write_report(out, 'flood_intelligence_benchmark', benchmark_report)
    if protected_hashes(root) != protected:
        raise RuntimeError('Phase 4E protected code changed during audit')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    source_paths = [p for base in ('flood', 'risk', 'citizen', 'research')
                    for p in (root / 'src/jalrakshak_ml' / base).glob('*.py')]
    packages = {}
    for name in ('numpy', 'torch', 'rasterio', 'shapely', 'pyproj', 'pydantic'):
        packages[name] = importlib.metadata.version(name)
    reproducibility = {'git_commit': commit, 'python': sys.version, 'os': platform.platform(),
                       'created_at': datetime.now(UTC).isoformat(), 'packages': packages, 'seed': 26071,
                       'solver': solver, 'claim_gates': gates, 'protected_phase4e_hashes': protected,
                       'source_hashes': {str(p.relative_to(root)): sha(p) for p in source_paths},
                       'report_hashes': {str(p.relative_to(out)): sha(p) for p in out.glob('*.json') if p.name.startswith(('phase11_', 'fno_smoke', 'final_ml_', 'flood_intelligence')) and 'reproducibility' not in p.name},
                       'config_hashes': {'configs/flood/phase5_executable_v1.yaml': sha(root / 'configs/flood/phase5_executable_v1.yaml')},
                       'PHASE4E_TRAINING_FILES_TOUCHED': False, 'LOCKED_TEST_ACCESSED': False,
                       'audit_only': audit_only, 'strict': strict, 'blockers': blockers}
    write_report(out, 'phase11_reproducibility_manifest', reproducibility)
    print(json.dumps({'status': 'AUDIT_COMPLETE_WITH_SCIENTIFIC_BLOCKERS', 'gates': gates,
                      'output_dir': str(out), 'execution_failures': failures}, indent=2))
    return 2 if strict and (failures or not gates['PHYSICS_DATASET_READY']) else (1 if failures else 0)
