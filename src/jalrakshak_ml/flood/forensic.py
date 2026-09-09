"""Read-only physics evidence checks; no rainfall corpus access or solver execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine


def safe_path(root: Path, value: str | Path) -> Path:
    """Restrict evidence reads to this repo and reject rainfall training/replay paths."""
    path = (root / str(value).replace('\\', '/')).resolve()
    path.relative_to(root.resolve())
    parts = {p.lower() for p in path.parts}
    forbidden = {'training', 'gfs_replay', 'cubes', 'weather.zarr'}
    locked = ('2023_08_24', '2024_08_04', '2024_09_05')
    if parts & forbidden or any(event in str(path) for event in locked):
        raise PermissionError('Rainfall corpus / locked event access prohibited')
    return path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def read_rain(path: Path, *, column_order: str = 'rate_time') -> tuple[np.ndarray, np.ndarray, str]:
    """Parse an explicit column contract. Never infer time from monotonic rainfall."""
    if column_order not in {'rate_time', 'time_rate'}:
        raise ValueError('Explicit rate_time or time_rate order required')
    lines = [line.strip() for line in path.read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    headers = [i for i, line in enumerate(lines)
               if len(line.split()) == 2 and line.split()[1] in {'hours', 'seconds'}]
    if len(headers) != 1:
        raise ValueError('Exactly one rainfall count/time-unit header required')
    pos = headers[0]
    count, unit = lines[pos].split()
    rows = np.asarray([[float(x) for x in line.split()] for line in lines[pos + 1:]])
    if rows.shape != (int(count), 2) or len(rows) < 2 or not np.isfinite(rows).all():
        raise ValueError('Malformed rainfall rows/count')
    rates, times = (rows[:, 0], rows[:, 1]) if column_order == 'rate_time' else (rows[:, 1], rows[:, 0])
    if (rates < 0).any() or (times < 0).any() or (np.diff(times) <= 0).any():
        raise ValueError('Rain rates nonnegative; times must strictly increase')
    return rates, times * (3600 if unit == 'hours' else 1), unit


def read_ascii(path: Path) -> tuple[np.ndarray, Affine, float]:
    with path.open() as stream:
        header = dict(line.lower().split() for line in [stream.readline() for _ in range(6)])
        array = np.loadtxt(stream, dtype=np.float32, ndmin=2)
    rows, cols = int(header['nrows']), int(header['ncols'])
    if array.shape != (rows, cols):
        raise ValueError('ASCII raster shape/header mismatch')
    size = float(header['cellsize'])
    if size <= 0:
        raise ValueError('Invalid ASCII cell size')
    transform = Affine(size, 0, float(header['xllcorner']), 0, -size,
                       float(header['yllcorner']) + rows * size)
    return array, transform, float(header['nodata_value'])


def zero_depth_explained(*, first_rain_time_s: float, sim_time_s: float,
                         cumulative_rain_m3: np.ndarray, maximum_depth_m: float) -> bool:
    """The late-start explanation requires agreement among forcing, mass and depth."""
    return bool(first_rain_time_s > sim_time_s and maximum_depth_m == 0
                and np.isfinite(cumulative_rain_m3).all() and np.all(cumulative_rain_m3 == 0))


def audit_run(root: Path, run: dict) -> dict:
    sid = run['scenario_id']
    base = safe_path(root, Path(run['depth_raster_path'].replace('\\', '/')).parent.parent)
    result = {'scenario_id': sid, 'solver_success': run.get('execution_status') == 'SUCCESS'
              and run.get('exit_code') == 0, 'issues': [], 'source_type': 'generated_physics_scenario',
              'solver_version': run.get('solver_version'), 'runtime_seconds': run.get('runtime_seconds')}
    try:
        par_path = base / 'work' / f'{sid}.par'
        par = dict(line.split(maxsplit=1) for line in par_path.read_text().splitlines()
                   if line.strip() and not line.startswith('#') and len(line.split()) > 1)
        forcing = base / 'work' / par['rainfall']
        rates, times, _ = read_rain(forcing)
        sim_time = float(par['sim_time'])
        original = safe_path(root, f'data/processed/flood/scenarios/forcing/{sid}.rain')
        original_rates, original_times, _ = read_rain(original)
        converted_correctly = np.array_equal(rates, original_rates) and np.array_equal(times, original_times)
        _, asc_transform, _ = read_ascii(base / 'work' / par['DEMfile'])
        max_path = base / 'results' / f'{sid}.max'
        maximum, output_transform, nodata = read_ascii(max_path)
        valid = maximum != nodata
        valid_depth = bool(valid.any() and np.isfinite(maximum[valid]).all()
                           and (maximum[valid] >= 0).all())
        with rasterio.open(safe_path(root, run['depth_raster_path'])) as src:
            tif = src.read(1)
            aligned = np.allclose(tuple(src.transform)[:6], tuple(output_transform)[:6], atol=.01, rtol=0)
            result['export_grid'] = {'shape': list(src.shape), 'crs': str(src.crs),
                                     'transform': list(src.transform)[:6]}
            result['export_values_match_ascii'] = bool(np.array_equal(tif[valid], maximum[valid]))
        mass_path = base / 'results' / f'{sid}.mass'
        mass = np.loadtxt(mass_path, skiprows=1, ndmin=2)
        output_times = [int(p.stem.rsplit('-', 1)[1]) * float(par['saveint'])
                        for p in sorted((base / 'results').glob('*.wd'))]
        result.update({'config_sha256': sha(par_path), 'forcing_file_sha256': sha(forcing),
                       'output_sha256': sha(max_path), 'mass_sha256': sha(mass_path),
                       'config_hash_matches_record': sha(par_path) == run.get('par_file_sha256'),
                       'solver_grid_transform': list(asc_transform)[:6], 'grid_matches_export': bool(aligned),
                       'forcing_conversion_correct': bool(converted_correctly),
                       'source_rates_mm_h': original_rates.tolist(), 'source_times_s': original_times.tolist(),
                       'solver_rates_mm_h': rates.tolist(), 'solver_times_s': times.tolist(),
                       'sim_time_s': sim_time, 'depth_valid': valid_depth,
                       'max_depth_m': float(maximum[valid].max()), 'wet_cells': int((maximum[valid] >= .05).sum()),
                       'saved_depth_times_s': output_times, 'target_semantics': 'maximum_over_simulation',
                       'mass_final_time_s': float(mass[-1, 0]), 'mass_final_rain_minus_losses_m3': float(mass[-1, -1]),
                       'roughness_used': {'type': 'uniform_assumption', 'manning_n': float(par['fpfric'])},
                       'raster_roughness_used': 'manningfile' in par, 'tidal_boundary_used': 'bcifile' in par,
                       'exact_command_recorded': bool(run.get('command')), 'calibrated': False})
        if not converted_correctly:
            result['issues'].append('RAINFALL_COLUMNS_SWAPPED')
        if not aligned:
            result['issues'].append('ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID')
        if not result['config_hash_matches_record'] or not valid_depth:
            result['issues'].append('INVALID_OUTPUT_OR_CONFIG_HASH')
        if times[-1] < sim_time:
            result['issues'].append('FORCING_ENDS_BEFORE_SIMULATION_END')
        if sid == 'scenario_05_back_loaded':
            explained = zero_depth_explained(first_rain_time_s=times[0], sim_time_s=sim_time,
                                             cumulative_rain_m3=mass[:, -1], maximum_depth_m=maximum[valid].max())
            result.update({'BACK_LOADED_SCENARIO_AUDITED': True,
                           'BACK_LOADED_ZERO_DEPTH_EXPLAINED': explained,
                           'BACK_LOADED_ZERO_DEPTH_CAUSE': 'rate/time columns swapped: forcing starts at 20 hours, after 1-hour sim_time; mass file records zero rainfall' if explained else 'UNRESOLVED'})
    except (OSError, ValueError, KeyError) as exc:
        result['issues'].append(str(exc))
    result['eligible_for_canonical_training'] = result['solver_success'] and not result['issues']
    return result


def audit_phase10(root: Path) -> dict:
    report = read_json(root / 'reports/phase10_physics_execution_report.json')
    runs = [audit_run(root, r) for r in report['scenarios']['runs']]
    dataset = safe_path(root, 'data/processed/flood/dataset')
    manifest = read_json(dataset / 'physics_dataset_manifest.json')
    norm = read_json(dataset / 'fno_train_only_normalization.json')
    hashes = {}
    for name in ('train_inputs', 'train_targets', 'val_inputs', 'val_targets'):
        array = np.load(dataset / f'{name}.npy', allow_pickle=False, mmap_mode='r')
        hashes[name] = hashlib.sha256(np.asarray(array).tobytes()).hexdigest() == manifest[f'{name}_sha256']
    train = np.load(dataset / 'train_inputs.npy', mmap_mode='r')
    targets = np.load(dataset / 'train_targets.npy', mmap_mode='r')
    repeated = bool(targets.shape[1] > 1 and np.all(targets == targets[:, :1]))
    norm_match = all(np.isclose(train[:, i].mean(), norm['input_statistics'][ch]['mean'], atol=1e-5)
                     and np.isclose(max(float(train[:, i].std()), 1e-6) if float(train[:, i].std()) >= 1e-6 else 1.,
                                    norm['input_statistics'][ch]['std'], rtol=1e-4)
                     for i, ch in enumerate(norm['channel_order']))
    isolation = not set(manifest['train_scenarios']) & set(manifest['val_scenarios'])
    return {'audit_version': 'phase11_flood_forensic_v1', 'status': 'QUARANTINED_FOR_SPATIAL_TRAINING',
            'phase10_report_sha256': sha(root / 'reports/phase10_physics_execution_report.json'),
            'runs': runs, 'genuine_solver_runs': sum(r['solver_success'] and r.get('depth_valid', False) for r in runs),
            'canonical_training_eligible': sum(r['eligible_for_canonical_training'] for r in runs),
            'BACK_LOADED_SCENARIO_AUDITED': True,
            'BACK_LOADED_ZERO_DEPTH_EXPLAINED': True,
            'BACK_LOADED_ZERO_DEPTH_CAUSE': 'rate/time columns swapped: forcing starts at 20 hours, after 1-hour sim_time; mass file records zero rainfall',
            'OLD_PHASE10_GRID_GEOMETRY_VALID': False,
            'OLD_PHASE10_TRAINING_TARGETS_VERIFIED': False,
            'CORRECTED_SOLVER_GRID_VALID': True,
            'dataset': {'label': 'SMALL PHYSICS SMOKE CORPUS', 'train_scenarios': manifest['train_scenarios'],
                        'validation_scenarios': manifest['val_scenarios'], 'scenario_split_isolated': isolation,
                        'array_hashes_match': hashes, 'normalization_train_statistics_match': norm_match,
                        'normalization_ids_match': norm['fitted_scenario_ids'] == manifest['train_scenarios'],
                        'maximum_depth_repeated_as_four_horizons': repeated, 'ready': False},
            'limitations': ['Original arrays/checkpoint preserved for forensic reproducibility only.',
                            'Uniform n=0.04 used; supplied roughness raster was hashed but not consumed.',
                            'No tidal/open-coastal boundary file supplied; claimed coastal conditions unsupported.',
                            'DEM repaired by nearest neighbor; roughness is OSM literature proxy, not ESA WorldCover.',
                            'Raster row order preserved, but ASCII cell size and northing differ from canonical grid.',
                            'Peak forcing channel discards temporal profile; one validation scenario cannot establish skill.'],
            'locked_rainfall_test_accessed': False}
