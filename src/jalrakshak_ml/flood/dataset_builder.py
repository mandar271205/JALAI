"""Compatibility entry point rejecting the quarantined Phase 10 batch format.

Use verified_dataset.build_verified_dataset for explicit target-time, grid and
forcing evidence. Original Phase 10 arrays remain untouched for reproducibility.
"""
from __future__ import annotations

import json
from pathlib import Path


def build_physics_dataset(batch_manifest_path: str | Path, *, domain_record_path: str | Path,
                          output_dir: str | Path, val_fraction: float = .25,
                          min_scenarios: int = 2):
    manifest = json.loads(Path(batch_manifest_path).read_text())
    for record in manifest.get('runs', []):
        if 'susceptibility' in str(record.get('depth_raster_path', '')).lower():
            raise ValueError('Susceptibility raster detected in physics targets')
    raise PermissionError(
        'Legacy peak-depth batch builder disabled: maximum raster was repeated as four horizons. '
        'Use verified_dataset.build_verified_dataset with explicit solver time/grid/forcing provenance.'
    )
