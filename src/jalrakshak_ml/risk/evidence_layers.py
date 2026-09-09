"""Evidence-backed local exposure and geophysical vulnerability rasters."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.enums import MergeAlg
from rasterio.features import rasterize
from shapely.geometry import box, shape
from shapely.ops import transform as transform_geometry

from jalrakshak_ml.flood.forensic import read_json, safe_path, sha


def exposure_layer(path: Path, *, grid_profile: dict, source: str,
                   source_date: str | None = None, expected_sha: str | None = None) -> tuple[dict, np.ndarray | None]:
    if not path.is_file():
        return {'status': 'UNAVAILABLE', 'missing_data': True, 'feature_count': None,
                'source': source, 'absence_means_no_assets': False}, None
    digest = sha(path)
    if expected_sha and digest != expected_sha:
        raise ValueError(f'Exposure source hash mismatch: {path}')
    data = read_json(path)
    crs = data.get('crs', {}).get('properties', {}).get('name', 'EPSG:4326')
    transformer = pyproj.Transformer.from_crs(crs, grid_profile['crs'], always_xy=True)
    t = grid_profile['transform']
    height, width = grid_profile['height'], grid_profile['width']
    domain = box(t.c, t.f + height * t.e, t.c + width * t.a, t.f)
    geometries, invalid, outside, duplicates = [], 0, 0, 0
    seen = set()
    for index, feature in enumerate(data.get('features', [])):
        props = feature.get('properties') or {}
        identity = (props.get('element'), props.get('id', index))
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        try:
            geometry = shape(feature.get('geometry'))
            if not geometry.is_valid or geometry.is_empty:
                invalid += 1
                continue
            projected = transform_geometry(transformer.transform, geometry)
            clipped = projected.intersection(domain)
            if clipped.is_empty:
                outside += 1
                continue
            geometries.append(clipped)
        except (ValueError, TypeError, KeyError):
            invalid += 1
    values = rasterize([(g, 1) for g in geometries], out_shape=(height, width),
                       transform=t, merge_alg=MergeAlg.add, all_touched=True, dtype='float32') if geometries else np.zeros((height, width), dtype='float32')
    return {'status': 'AVAILABLE' if geometries else 'EMPTY_MAPPING', 'missing_data': not bool(geometries),
            'source': source, 'source_date': source_date, 'source_sha256': digest,
            'retrieval_provenance': 'local OSM snapshot; source manifest timestamp where available',
            'source_crs': crs, 'crs': str(grid_profile['crs']), 'shape': [height, width],
            'transform': list(t)[:6], 'feature_count': len(geometries), 'invalid_geometry_count': invalid,
            'outside_domain_count': outside, 'duplicate_count': duplicates,
            'raw_feature_count': len(data.get('features', [])), 'processing': 'reproject, exact domain clip, rasterize ADD',
            'representation': 'feature-cell intersection count; not population, unique facilities or length density',
            'occupied_cells': int((values > 0).sum()), 'absence_means_no_assets': False,
            'completeness': 'OSM coverage unknown; empty mapped cells do not establish asset absence'}, values


def build_exposure(root: Path) -> tuple[dict, np.ndarray, np.ndarray, dict]:
    root = Path(root).resolve()
    static = safe_path(root, 'data/processed/static')
    with rasterio.open(static / 'elevation.tif') as src:
        profile = src.profile.copy()
        domain_mask = src.read_masks(1).astype(bool) & np.isfinite(src.read(1))
    cache_npz = root / 'data/processed/flood/physics_outputs/phase11_products/risk_layers.npz'
    cache_rep = root / 'reports/phase11_exposure_evidence.json'
    if cache_npz.is_file() and cache_rep.is_file():
        try:
            with np.load(cache_npz) as data:
                if 'exposure' in data and data['exposure'].shape == (profile['height'], profile['width']):
                    report = read_json(cache_rep)
                    if report.get('status') == 'PARTIAL_MAPPED_ASSETS' and 'layers' in report:
                        return report, data['exposure'].astype('float32'), domain_mask, profile
        except (OSError, ValueError, KeyError):
            pass
    manifest = read_json(static / 'osm_manifest.json')
    classes = ('hospitals', 'schools', 'roads', 'railways', 'emergency_assets', 'bridges', 'shelters', 'buildings', 'power')
    report, grids = {}, {}
    for name in classes:
        path = static / f'{name}.geojson'
        if not path.is_file():
            path = safe_path(root, f'data/raw/osm/{name}.geojson')
        record, values = exposure_layer(path, grid_profile=profile,
                                        source='OpenStreetMap', source_date=manifest.get('acquisition_timestamp'),
                                        expected_sha=manifest.get('checksums', {}).get(name))
        report[name] = record
        if values is not None and record['status'] == 'AVAILABLE':
            grids[name] = values
    if not grids:
        raise ValueError('No genuine mapped exposure layers available')
    # Mapped presence equally weighted across available classes; no invented population counts.
    exposure = np.mean([np.clip(v, 0, 1) for v in grids.values()], axis=0).astype('float32')
    return {'version': 'phase11_exposure_v1', 'status': 'PARTIAL_MAPPED_ASSETS', 'layers': report,
            'normalization': 'presence per class [0,1]; equal weight over available classes',
            'population_available': False, 'calibrated_weights': False,
            'missing_classes': [c for c in classes if c not in grids],
            'coverage_assumption': 'relative risk conditional on mapped assets only'}, exposure, domain_mask, profile


def build_vulnerability(root: Path, profile: dict) -> tuple[dict, np.ndarray, np.ndarray]:
    root = Path(root).resolve()
    # Deliberately structural/geophysical factors only. No inference about income or demography.
    specs = {'elevation': (0., 50., 'decreasing'), 'slope': (0., 15., 'decreasing'),
             'distance_to_water': (0., 2000., 'decreasing')}
    factors, values, masks = {}, [], []
    for name, (low, high, direction) in specs.items():
        path = safe_path(root, f'data/processed/static/{name}.tif')
        if not path.is_file():
            factors[name] = {'status': 'UNAVAILABLE'}
            continue
        with rasterio.open(path) as src:
            if src.crs != profile['crs'] or src.transform != profile['transform'] or src.shape != (profile['height'], profile['width']):
                raise ValueError(f'Vulnerability grid mismatch: {name}')
            raw = src.read(1)
            mask = src.read_masks(1).astype(bool) & np.isfinite(raw)
        if not mask.any():
            factors[name] = {'status': 'UNAVAILABLE'}
            continue
        score = 1 - np.clip((raw - low) / (high - low), 0, 1)
        score[~mask] = 0
        values.append(score)
        masks.append(mask)
        factors[name] = {'status': 'AVAILABLE_PROXY', 'source_path': str(path.relative_to(root)),
                         'sha256': sha(path), 'directionality': direction, 'bounds': [low, high],
                         'normalization': '1 - clip((x-low)/(high-low),0,1)',
                         'weight_rationale': 'equal expert proxy weights; uncalibrated sensitivity assumptions',
                         'missing_data': 'exclude from supervision/risk; never replace by low vulnerability',
                         'valid_cells': int(mask.sum())}
    if not values:
        raise ValueError('No supported geophysical vulnerability factors')
    valid = np.logical_and.reduce(masks)
    result = np.mean(values, axis=0).astype('float32')
    result[~valid] = 0
    return {'version': 'phase11_vulnerability_v1', 'status': 'GEOPHYSICAL_PROXY_ONLY', 'factors': factors,
            'social_vulnerability_available': False, 'calibrated': False,
            'factor_weight': 1 / len(values), 'valid_cells': int(valid.sum()),
            'limitations': ['Correlated terrain factors can double-count susceptibility; require ablation/calibration.',
                            'Drainage capacity, building structure, income, age, disability and population unavailable.']}, result, valid
