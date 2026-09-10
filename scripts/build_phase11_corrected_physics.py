"""Explicit small CPU solver corpus and dataset, without FNO/rainfall training."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jalrakshak_ml.flood.forensic import read_ascii, sha
from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
from jalrakshak_ml.flood.scenarios import get_default_scenario_batch
from jalrakshak_ml.flood.verified_dataset import build_verified_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/flood/physics_outputs/phase11_corpus_v1')
    args = parser.parse_args()
    if not args.execute:
        print('Plan: six 1-hour generated scenarios; square solver subdomain, five train/one validation; no training.')
        return 0
    out = args.output_dir.resolve()
    if out.exists():
        raise FileExistsError('Choose a new immutable corpus directory')
    out.mkdir(parents=True)
    original = ROOT / 'data/processed/static/elevation_repaired.tif'
    dem = out / 'elevation_square.tif'
    with rasterio.open(original) as src:
        size = abs(src.transform.e)
        width = math.floor((src.bounds.right - src.bounds.left) / size)
        height = src.height
        transform = from_origin(src.bounds.left, src.bounds.top, size, size)
        profile = src.profile.copy()
        profile.update(width=width, height=height, transform=transform, nodata=-9999.)
        elevation = np.full((height, width), -9999., dtype='float32')
        reproject(src.read(1), elevation, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs=src.crs, src_nodata=src.nodata,
                  dst_nodata=-9999., resampling=Resampling.bilinear)
        if (elevation == -9999).any() or not np.isfinite(elevation).all():
            raise ValueError('Corrected solver subdomain contains missing DEM cells')
        source_bounds = list(src.bounds)
    def write_array(path, array):
        with rasterio.open(path, 'w', **profile) as dst:
            dst.write(np.asarray(array, dtype='float32'), 1)
    write_array(dem, elevation)
    roughness = out / 'roughness_uniform.tif'
    write_array(roughness, np.full((height, width), .04))
    def provenance(path, source):
        return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'source': source}
    dem_prov = {**provenance(dem, 'explicit bilinear reproject of repaired Copernicus DEM'),
                'original_sha256': sha(original), 'repair': 'inherited nearest-neighbor DEM repair'}
    rough_prov = provenance(roughness, 'uniform n=0.04 consumed as fpfric; uncalibrated literature assumption')
    records, runs = [], []
    scenarios = get_default_scenario_batch(6)
    for i, scenario in enumerate(scenarios):
        print(f'Running corrected {scenario.scenario_id}', flush=True)
        rain, _ = scenario.write_forcing(out / 'forcing')
        run_dir = out / scenario.scenario_id
        run = run_lisflood_smoke(dem_path=dem, roughness_path=roughness, bdy_path=rain,
                                output_dir=run_dir, scenario_id=scenario.scenario_id,
                                executable='wsl:/usr/local/bin/lisflood', sim_time_hours=1.)
        runs.append(run.to_dict())
        if run.execution_status != 'SUCCESS':
            raise RuntimeError(f'Solver failed: {run.stderr_tail}')
        # Use actual final-time depth, not .max. Last mass time verifies save horizon.
        raw = run_dir / 'results' / f'{scenario.scenario_id}-0002.wd'
        depth, raw_transform, nodata = read_ascii(raw)
        mass = np.loadtxt(run_dir / 'results' / f'{scenario.scenario_id}.mass', skiprows=1)
        if mass[-1, 0] != 3600 or (depth == nodata).any() or not np.allclose(list(raw_transform)[:6], list(transform)[:6], atol=.02, rtol=0):
            raise ValueError('Final solver output time/grid/nodata invalid')
        target = run_dir / 'final_depth_3600s.tif'
        write_array(target, depth)
        layers = {'elevation': dem_prov, 'roughness': rough_prov}
        for j, rate in enumerate(scenario.rates_mm_h):
            path = run_dir / f'rain_interval_{j}.tif'
            write_array(path, np.full((height, width), rate))
            layers[f'rain_interval_{j}'] = provenance(path, 'generated_physics_scenario interval rate mm/h')
        record = {'scenario_id': scenario.scenario_id, 'split': 'validation' if i == 5 else 'train',
                  'solver_version': run.solver_version, 'solver_run_id': scenario.scenario_id,
                  'solver_success': True, 'source_type': 'generated_physics_scenario',
                  'forcing_provenance': scenario.to_dict(), 'dem_provenance': dem_prov,
                  'roughness_provenance': rough_prov, 'static_provenance': {'elevation': dem_prov, 'roughness': rough_prov},
                  'crs': 'EPSG:32643', 'transform': list(transform)[:6], 'cell_size': [size, size],
                  'target_units': 'm', 'target_shape': [height, width], 'target_time_seconds': 3600,
                  'output_path': str(target.relative_to(ROOT)), 'output_sha256': sha(target),
                  'raw_output_path': str(raw.relative_to(ROOT)), 'raw_output_sha256': sha(raw),
                  'forcing_path': str(rain.relative_to(ROOT)), 'forcing_sha256': sha(rain),
                  'config_path': str((run_dir / 'work' / f'{scenario.scenario_id}.par').relative_to(ROOT)),
                  'config_sha256': run.par_file_sha256, 'runtime_seconds': run.runtime_seconds,
                  'generated_at': datetime.now(UTC).isoformat(), 'dataset_version': 'phase11_square_smoke_v1',
                  'command': run.command, 'hazard_type': 'lisflood_simulated_depth', 'spatial_audit_passed': True,
                  'forcing_audit_passed': True, 'input_layers': layers,
                  'run_record_path': str((run_dir / f'{scenario.scenario_id}_run_record.json').relative_to(ROOT)),
                  'run_record_sha256': sha(run_dir / f'{scenario.scenario_id}_run_record.json')}
        records.append(record)
    manifest = {'dataset_version': 'phase11_square_smoke_v1', 'records': records,
                'input_channels': ['elevation', 'roughness', 'rain_interval_0', 'rain_interval_1'],
                'grid_note': 'Explicit square subdomain; east edge cropped inward, no canonical grid mutation.',
                'original_bounds': source_bounds, 'solver_bounds': list(rasterio.transform.array_bounds(height, width, transform)),
                'limitations': ['SMALL PHYSICS SMOKE CORPUS', 'Uniform uncalibrated roughness; dry initial condition.',
                                'No explicit tidal boundary, infiltration, urban drains or calibrated channels.',
                                'Actual final-depth targets at 60 minutes only; no 90/120 minute targets.']}
    manifest_path = out / 'sample_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False))
    built = build_verified_dataset(ROOT, manifest_path, out / 'dataset')
    summary = {'status': 'SMALL_PHYSICS_SMOKE_CORPUS', 'manifest_path': str(manifest_path.relative_to(ROOT)),
               'manifest_sha256': sha(manifest_path), 'dataset_dir': str((out / 'dataset').relative_to(ROOT)),
               'dataset_reference_sha256': sha(out / 'dataset/physics_reference_manifest.json'),
               'normalization_sha256': sha(out / 'dataset/fno_train_only_normalization.json'),
               'train_scenarios': 5, 'validation_scenarios': 1, 'target_time_seconds': 3600,
               'shape': [height, width], 'FNO_TRAINING_EXECUTED': False,
               'limitations': manifest['limitations'], 'runs': runs, 'dataset_version': built['dataset_version']}
    (out / 'corpus_report.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({k: v for k, v in summary.items() if k != 'runs'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
