"""One explicit CPU solver rerun in a new directory; original Phase 10 retained."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from jalrakshak_ml.flood.forensic import sha
from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
from jalrakshak_ml.flood.scenarios import get_default_scenario_batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='data/processed/flood/physics_outputs/phase11_back_loaded_v1')
    args = parser.parse_args()
    out = Path(args.output_dir)
    if out.exists():
        raise FileExistsError('Diagnostic run output is immutable; choose a new version')
    out.mkdir(parents=True)
    source = Path('data/processed/static/elevation_repaired.tif')
    square = out / 'solver_dem_square.tif'
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(src.crs, src.crs, src.width, src.height,
                                                              *src.bounds, resolution=abs(src.transform.e))
        array = np.full((height, width), -9999., dtype='float32')
        reproject(src.read(1), array, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs=src.crs, src_nodata=src.nodata,
                  dst_nodata=-9999., resampling=Resampling.bilinear)
        profile = src.profile.copy()
        profile.update(transform=transform, width=width, height=height, nodata=-9999.)
        with rasterio.open(square, 'w', **profile) as dst:
            dst.write(array, 1)
    scenario = get_default_scenario_batch(6)[4]
    forcing, _ = scenario.write_forcing(out / 'forcing')
    run = run_lisflood_smoke(dem_path=square, roughness_path='data/processed/static/roughness.tif',
                            bdy_path=forcing, output_dir=out / 'run', scenario_id='back_loaded_corrected_v1',
                            executable='wsl:/usr/local/bin/lisflood', sim_time_hours=1.)
    record = {**run.to_dict(), 'diagnostic_only': True, 'eligible_for_training': False,
              'source_type': 'generated_physics_scenario', 'source_dem_sha256': sha(source),
              'solver_dem_sha256': sha(square), 'solver_grid': {'shape': [height, width],
              'transform': list(transform)[:6], 'crs': 'EPSG:32643'},
              'forcing_integral_mm': 50., 'original_phase10_outputs_modified': False,
              'roughness_used': 'uniform n=0.04; raster not used',
              'boundary': 'solver default; no tidal or coastal calibration',
              'command': run.command,
              'work_directory': str((out / 'run/work').resolve())}
    (out / 'diagnostic_manifest.json').write_text(json.dumps(record, indent=2, allow_nan=False))
    print(json.dumps(record, indent=2))
    return 0 if run.execution_status == 'SUCCESS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
