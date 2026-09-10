"""Strict, scenario-split dataset builder for fully evidenced future solver runs."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio

from .forensic import read_ascii, read_json, safe_path, sha


def validate_sample(root: Path, record: dict) -> np.ndarray:
    required = ('scenario_id', 'solver_version', 'solver_run_id', 'forcing_provenance',
                'dem_provenance', 'roughness_provenance', 'static_provenance', 'crs',
                'transform', 'cell_size', 'target_shape', 'target_time_seconds', 'output_path',
                'output_sha256', 'forcing_path', 'forcing_sha256', 'config_path', 'config_sha256',
                'runtime_seconds', 'generated_at', 'dataset_version', 'command',
                'raw_output_path', 'raw_output_sha256', 'run_record_path', 'run_record_sha256')
    if 'susceptibility' in str(record.get('output_path', '')).lower() or record.get('hazard_type') == 'susceptibility':
        raise ValueError('Susceptibility raster detected in physics targets')
    if any(key not in record or record[key] is None for key in required):
        raise ValueError('Missing solver sample provenance')
    if record.get('solver_success') is not True or record.get('source_type') != 'generated_physics_scenario':
        raise ValueError('Only successful generated physics scenarios accepted')
    if record.get('target_units') != 'm' or record.get('hazard_type') != 'lisflood_simulated_depth':
        raise ValueError('Target must be LISFLOOD simulated depth in metres')
    if not record.get('spatial_audit_passed') or not record.get('forcing_audit_passed'):
        raise ValueError('Grid and forcing audit required')
    if record['runtime_seconds'] <= 0 or record['target_time_seconds'] <= 0 or datetime.fromisoformat(record['generated_at']).tzinfo is None:
        raise ValueError('Positive solver runtime/target time and timezone timestamp required')
    for name in ('output', 'forcing', 'config'):
        if sha(safe_path(root, record[f'{name}_path'])) != record[f'{name}_sha256']:
            raise ValueError(f'{name} hash mismatch')
    for provenance in (record['dem_provenance'], record['roughness_provenance'], *record['static_provenance'].values()):
        if not provenance.get('source') or sha(safe_path(root, provenance['path'])) != provenance['sha256']:
            raise ValueError('Static provenance/hash mismatch')
    raw_path, run_path = safe_path(root, record['raw_output_path']), safe_path(root, record['run_record_path'])
    if sha(raw_path) != record['raw_output_sha256'] or sha(run_path) != record['run_record_sha256']:
        raise ValueError('Raw solver output/run record hash mismatch')
    run = read_json(run_path)
    if run.get('execution_status') != 'SUCCESS' or run.get('exit_code') != 0 or not run.get('physically_simulated') or run.get('solver_version') != record['solver_version'] or run.get('command') != record['command']:
        raise ValueError('Successful solver invocation evidence mismatch')
    raw_values, raw_transform, _ = read_ascii(raw_path)
    with rasterio.open(safe_path(root, record['output_path'])) as src:
        values = src.read(1)
        if str(src.crs) != record['crs'] or list(src.shape) != record['target_shape'] or not np.allclose(list(src.transform)[:6], record['transform'], atol=1e-5, rtol=0):
            raise ValueError('Target grid mismatch')
        if not src.read_masks(1).all() or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError('Invalid depth: nodata, NaN/Inf or negative target')
        if not np.array_equal(values, raw_values) or not np.allclose(list(src.transform)[:6], list(raw_transform)[:6], atol=.02, rtol=0):
            raise ValueError('GeoTIFF must faithfully represent raw solver depth and grid')
    return values


def build_verified_dataset(root: Path, manifest_path: Path, output_dir: Path) -> dict:
    manifest = read_json(manifest_path)
    records = manifest.get('records', [])
    ids = [r['scenario_id'] for r in records]
    if not records or len(ids) != len(set(ids)):
        raise ValueError('Unique scenario IDs required; no pixel-random splitting')
    if {r.get('split') for r in records} != {'train', 'validation'}:
        raise ValueError('Explicit train and validation scenario splits required')
    if output_dir.exists():
        raise FileExistsError('Dataset version output must be new')
    channels = manifest['input_channels']
    loaded = {}
    grid = None
    for r in records:
        target = validate_sample(root, r)
        identity = (r['crs'], r['transform'], r['target_shape'], r['target_time_seconds'])
        if grid is not None and grid != identity:
            raise ValueError('All samples need the same grid and target time semantics')
        grid = identity
        inputs = []
        for channel in channels:
            p = r['input_layers'][channel]
            if sha(safe_path(root, p['path'])) != p['sha256']:
                raise ValueError('Input hash mismatch')
            with rasterio.open(safe_path(root, p['path'])) as src:
                if str(src.crs) != r['crs'] or list(src.shape) != r['target_shape'] or not np.allclose(list(src.transform)[:6], r['transform']):
                    raise ValueError('Input grid mismatch')
                values = src.read(1)
                if not src.read_masks(1).all() or not np.isfinite(values).all():
                    raise ValueError('Missing static input; no implicit fill')
                inputs.append(values)
        loaded[r['scenario_id']] = (np.stack(inputs), target[None, None])
    train_ids = [r['scenario_id'] for r in records if r['split'] == 'train']
    train_x = np.stack([loaded[s][0] for s in train_ids]).astype('float32')
    stats = {ch: {'mean': float(train_x[:, i].mean()), 'std': max(float(train_x[:, i].std()), 1e-6)}
             for i, ch in enumerate(channels)}
    normalization = {'normalization_version': 'phase5_fno_train_only_v1', 'status': 'PASS',
                     'fitted_split': 'train', 'fitted_scenario_ids': train_ids, 'channel_order': channels,
                     'input_statistics': stats, 'validation_opened': False, 'test_opened': False,
                     'scope': 'fit computation uses only train tensors'}
    output_dir.mkdir(parents=True)
    for split, prefix in [('train', 'train'), ('validation', 'val')]:
        selected = [loaded[r['scenario_id']] for r in records if r['split'] == split]
        np.save(output_dir / f'{prefix}_inputs.npy', np.stack([v[0] for v in selected]))
        np.save(output_dir / f'{prefix}_targets.npy', np.stack([v[1] for v in selected]))
    (output_dir / 'fno_train_only_normalization.json').write_text(json.dumps(normalization, indent=2, allow_nan=False))
    output = {**manifest, 'status': 'FROZEN', 'corpus_label': 'SMALL PHYSICS SMOKE CORPUS',
              'target_quantity': 'physics_simulated_water_depth', 'physics_reference': True,
              'target_semantics': 'single_explicit_solver_time; no repeated maxima',
              'records': [{**r, 'physically_simulated': True, 'physics_reference': True} for r in records]}
    import hashlib
    output['manifest_content_sha256'] = hashlib.sha256(json.dumps(output, sort_keys=True, allow_nan=False).encode()).hexdigest()
    (output_dir / 'physics_reference_manifest.json').write_text(json.dumps(output, indent=2, allow_nan=False))
    return output
