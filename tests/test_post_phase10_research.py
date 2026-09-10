"""Phase 11 scientific contracts tested with isolated fixtures, never rainfall data."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from jalrakshak_ml.citizen.metadata_verifier import MetadataVerifier
from jalrakshak_ml.citizen.verification_v2 import CitizenReportV2
from jalrakshak_ml.core.claim_gates import get_phase10_executed_gates
from jalrakshak_ml.flood.dataset_builder import build_physics_dataset
from jalrakshak_ml.flood.forecast_to_forcing import (
    GridSpec,
    forecast_to_forcing,
    write_interval_rain,
)
from jalrakshak_ml.flood.forensic import audit_run, read_rain, safe_path, sha, zero_depth_explained
from jalrakshak_ml.flood.lisflood_adapter import ensure_ascii_dem, ensure_lisflood_rain
from jalrakshak_ml.flood.smoke_evaluation import depth_metrics, scenario_summary
from jalrakshak_ml.flood.verified_dataset import build_verified_dataset, validate_sample
from jalrakshak_ml.research.post_physics import claim_gates
from jalrakshak_ml.risk.evidence_layers import build_vulnerability, exposure_layer
from jalrakshak_ml.risk.scenario_risk import evaluate_risk, explain_cell, scenario_uncertainty
from jalrakshak_ml.serving.flood_evidence_contracts import FloodEvidenceArtifact


def raster(path: Path, values=None, *, dy=100):
    values = np.ones((2, 2), dtype='float32') if values is None else values.astype('float32')
    profile = {'driver': 'GTiff', 'width': 2, 'height': 2, 'count': 1, 'dtype': 'float32',
               'crs': 'EPSG:32643', 'transform': from_origin(260000, 2100000, 100, dy)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, 'w', **profile) as dst:
        dst.write(values, 1)
    return profile


@pytest.mark.parametrize('rates', [(20., 80.), (80., 20.), (15., 15.)])
def test_explicit_forcing_order_and_conservation(tmp_path, rates):
    raw = tmp_path / 'input.rain'
    report = write_interval_rain(raw, np.asarray(rates))
    converted = ensure_lisflood_rain(raw, tmp_path / 'out')
    values, times, unit = read_rain(converted)
    assert values[0] == rates[0] and values[-1] == rates[-1]
    assert times[0] == 0 and times[-1] == 3600 and unit == 'seconds'
    assert report['accumulation_mm'] == pytest.approx(sum(rates) / 2)


def test_rain_parser_rejects_nonmonotonic_times(tmp_path):
    path = tmp_path / 'bad.rain'
    path.write_text('# test\n2 seconds\n20 5\n80 0\n')
    with pytest.raises(ValueError):
        read_rain(path)


def test_ascii_rejects_rectangular_grid_and_fake_dem(tmp_path):
    path = tmp_path / 'rect.tif'
    raster(path, dy=200)
    with pytest.raises(ValueError, match='square'):
        ensure_ascii_dem(path, tmp_path / 'out')
    path.write_bytes(b'invalid')
    with pytest.raises(rasterio.errors.RasterioIOError):
        ensure_ascii_dem(path, tmp_path / 'out')


@pytest.mark.parametrize('value', ['data/processed/training/file.json', 'data/processed/gfs_replay/a',
                                  'data/raw/mumbai_monsoon_2023_08_24/a', '../outside.json'])
def test_forbidden_paths_rejected_before_open(tmp_path, value):
    with pytest.raises((ValueError, PermissionError)):
        safe_path(tmp_path, value)


def forcing_args():
    grid = GridSpec('EPSG:32643', (2, 2), (100, 0, 260000, 0, -100, 2100000))
    return dict(issue_time='2021-01-01T00:00:00+00:00', horizons_minutes=(30, 60, 90, 120),  # noqa: C408
                values=np.ones((1, 4, 2, 2)) * 10, valid_mask=np.ones((1, 4, 2, 2), dtype=bool),
                units='mm/h', quantity='interval_mean_rate', grid=grid, target_grid=grid,
                model_version='future-contract-fixture', data_version='fixture', providers=('fixture',),
                quality=.8, confidence=.4, scenario_ids=('s1',), scenario_weights=(1.,))


def test_forecast_rate_accumulation_equivalence():
    kwargs = forcing_args()
    rates = forecast_to_forcing(**kwargs)
    kwargs.update(values=kwargs['values'] / 2, units='mm', quantity='interval_accumulation')
    accumulation = forecast_to_forcing(**kwargs)
    np.testing.assert_array_equal(rates['rates_mm_h'], accumulation['rates_mm_h'])
    assert rates['source_type'] == 'forecast_model_output' and not rates['observed']
    assert rates['quality'] != rates['confidence']


@pytest.mark.parametrize('change', [{'source_type': 'observed_historical_gpm'}, {'units': 'mm'},
                                   {'horizons_minutes': (60, 120, 180, 240)}, {'quality': float('nan')}])
def test_forecast_contract_rejects_ambiguous_inputs(change):
    args = forcing_args()
    args.update(change)
    with pytest.raises(ValueError):
        forecast_to_forcing(**args)


def test_missing_rainfall_is_not_filled():
    args = forcing_args()
    args['valid_mask'][0, 0, 0, 0] = False
    with pytest.raises(ValueError, match='Unavailable'):
        forecast_to_forcing(**args)


def test_missing_exposure_is_not_zero_asset_evidence(tmp_path):
    meta, values = exposure_layer(tmp_path / 'absent.geojson', grid_profile={}, source='OSM')
    assert values is None and meta['feature_count'] is None and meta['missing_data']
    assert not meta['absence_means_no_assets']


def test_exposure_geometry_and_duplicate_validation(tmp_path):
    path = tmp_path / 'facilities.geojson'
    profile = raster(tmp_path / 'dem.tif')
    feature = {'type': 'Feature', 'properties': {'element': 'node', 'id': 1},
               'geometry': {'type': 'Point', 'coordinates': [260050, 2099950]}}
    path.write_text(json.dumps({'crs': {'properties': {'name': 'EPSG:32643'}}, 'features': [feature, feature]}))
    report, grid = exposure_layer(path, grid_profile=profile, source='fixture')
    assert report['duplicate_count'] == 1 and report['feature_count'] == 1
    assert grid.sum() == 1


def test_vulnerability_requires_real_factors(tmp_path):
    profile = raster(tmp_path / 'dem.tif')
    with pytest.raises(ValueError, match='No supported'):
        build_vulnerability(tmp_path, profile)


def risk(value=.6, kind='susceptibility'):
    a = np.full((2, 2), value)
    return evaluate_risk(a, np.ones_like(a), np.ones_like(a), np.ones_like(a, dtype=bool),
                         hazard_type=kind, units='relative_index' if kind == 'susceptibility' else 'm',
                         hazard_scale=1., provenance={'hazard': 'fixture_h', 'exposure': 'fixture_e', 'vulnerability': 'fixture_v'},
                         quality=.8, confidence=None)


def test_risk_preserves_hazard_and_exact_decomposition():
    result = risk(kind='lisflood_simulated_depth')
    assert result['hazard_type'] == 'lisflood_simulated_depth'
    assert result['risk_score'][0, 0] == pytest.approx(.6)
    explanation = explain_cell(result, 0, 0)
    assert sum(f['contribution'] for f in explanation['factors']) == pytest.approx(.6)
    assert all(f['evidence_source'] for f in explanation['factors'])


def test_scenario_weighted_quantiles_and_frequencies():
    result = scenario_uncertainty([risk(.1), risk(.9)], np.array([.9, .1]))
    assert result['median'][0, 0] == .1
    assert result['expected_risk'][0, 0] == pytest.approx(.18)
    assert result['class_scenario_frequency']['LOW'][0, 0] == .9
    assert not result['calibrated_probability']
    with pytest.raises(ValueError, match='Cannot mix'):
        scenario_uncertainty([risk(), risk(kind='lisflood_simulated_depth')], np.array([.5, .5]))


def test_depth_metric_support_and_one_scenario_no_ci():
    target = np.array([[0., .2], [.1, 0.]])
    metric = depth_metrics(target, target, np.ones_like(target, dtype=bool))
    assert metric['mae_m'] == 0
    assert metric['thresholds']['0.3']['recall'] is None
    assert scenario_summary({'one': metric}, {'one': metric})['paired_mae_difference_interval_95'] is None


def test_citizen_future_timestamp_duplicates_and_manual_review():
    def report(id, stamp):
        return CitizenReportV2(id, 'fixture', stamp, 19., 72.9, None, 'flood', None, 'water on street')
    first = report('a', '2025-01-01T00:20:00+00:00')
    other = report('b', '2025-01-01T00:19:00+00:00')
    result = MetadataVerifier().verify(first, now=datetime(2025, 1, 1, tzinfo=UTC), neighbors=(other,))
    assert 'timestamp_in_future' in result['contradictions']
    assert result['needs_manual_review'] and not result['CITIZEN_ML_MODEL_AVAILABLE']
    assert result['rule_evidence'][3]['report_ids'] == ['b']


def test_claims_never_promote_smoke_or_rainfall_winner():
    gates = claim_gates(forensic={}, fno={'checkpoint_epoch': 2}, exposure={}, vulnerability={}, risk_ready=False, solver={})
    assert gates['FNO_ACTUALLY_TRAINED']
    assert not gates['FNO_SCIENTIFICALLY_VALIDATED'] and not gates['RAIN_FORECAST_WINNER_FROZEN']
    with pytest.raises(PermissionError, match='automatic promotion disabled'):
        get_phase10_executed_gates()


def test_serving_rejects_susceptibility_as_depth():
    with pytest.raises(ValueError):
        FloodEvidenceArtifact(run_id='x', generated_at=datetime.now(UTC), model_version='x', data_version='x',
                              hazard_type='susceptibility', units='m', raster_crs='EPSG:32643',
                              raster_transform=(100, 0, 0, 0, -100, 200), raster_shape=(2, 2),
                              artifact_path='fixture', artifact_sha256='a' * 64,
                              provenance={'source': 'fixture'}, uncertainty={'calibrated': False}, quality=.8,
                              status='experimental')


def sample_record(tmp_path, sid, value, split):
    path = tmp_path / f'{sid}.tif'
    profile = raster(path, np.full((2, 2), value))
    forcing, config = tmp_path / 'forcing.rain', tmp_path / 'run.par'
    if not forcing.exists():
        write_interval_rain(forcing, np.array([20., 80.]))
    config.write_text('fixture solver config')
    prov = {'path': str(path), 'sha256': sha(path), 'source': 'fixture'}
    raw = tmp_path / f'{sid}.wd'
    raw.write_text('ncols 2\nnrows 2\nxllcorner 260000\nyllcorner 2099800\ncellsize 100\nNODATA_value -9999\n'
                   + f'{value} {value}\n{value} {value}\n')
    run = tmp_path / f'{sid}_run.json'
    run.write_text(json.dumps({'execution_status': 'SUCCESS', 'exit_code': 0,
                              'physically_simulated': True, 'solver_version': 'fixture', 'command': ['fixture']}))
    return {'scenario_id': sid, 'split': split, 'solver_version': 'fixture', 'solver_run_id': sid,
            'solver_success': True, 'source_type': 'generated_physics_scenario', 'forcing_provenance': {'source': 'fixture'},
            'dem_provenance': prov, 'roughness_provenance': prov, 'static_provenance': {'x': prov},
            'crs': 'EPSG:32643', 'transform': list(profile['transform'])[:6], 'cell_size': [100, 100],
            'target_units': 'm', 'target_shape': [2, 2], 'target_time_seconds': 3600,
            'output_path': str(path), 'output_sha256': sha(path), 'forcing_path': str(forcing), 'forcing_sha256': sha(forcing),
            'config_path': str(config), 'config_sha256': sha(config), 'runtime_seconds': 1,
            'generated_at': datetime.now(UTC).isoformat(), 'dataset_version': 'fixture', 'command': ['fixture'],
            'hazard_type': 'lisflood_simulated_depth', 'spatial_audit_passed': True, 'forcing_audit_passed': True,
            'input_layers': {'x': prov}, 'raw_output_path': str(raw), 'raw_output_sha256': sha(raw),
            'run_record_path': str(run), 'run_record_sha256': sha(run)}


def test_verified_dataset_train_normalization_and_single_time(tmp_path):
    records = [sample_record(tmp_path, 'train', 1., 'train'), sample_record(tmp_path, 'val', 100., 'validation')]
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'records': records, 'input_channels': ['x']}))
    output = tmp_path / 'output'
    build_verified_dataset(tmp_path, manifest, output)
    norm = json.loads((output / 'fno_train_only_normalization.json').read_text())
    assert norm['input_statistics']['x']['mean'] == 1
    assert norm['fitted_scenario_ids'] == ['train']
    assert np.load(output / 'train_targets.npy').shape == (1, 1, 1, 2, 2)


@pytest.mark.parametrize('change', [{'solver_success': False}, {'target_units': 'relative_index'},
                                  {'source_type': 'heuristic'}, {'output_sha256': 'a' * 64},
                                  {'crs': 'EPSG:4326'}, {'spatial_audit_passed': False}])
def test_invalid_physics_samples_rejected(tmp_path, change):
    record = sample_record(tmp_path, 'sample', 1., 'train')
    record.update(change)
    with pytest.raises(ValueError):
        validate_sample(tmp_path, record)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1.])
def test_invalid_depth_not_filled(tmp_path, value):
    record = sample_record(tmp_path, 'sample', value, 'train')
    with pytest.raises(ValueError, match='Invalid depth'):
        validate_sample(tmp_path, record)


def test_legacy_builder_blocks_repeated_peak_targets(tmp_path):
    p = tmp_path / 'batch.json'
    p.write_text('{"runs": []}')
    with pytest.raises(PermissionError, match='repeated'):
        build_physics_dataset(p, domain_record_path=p, output_dir=tmp_path / 'out')


def test_missing_forensic_evidence_never_claims_eligible(tmp_path):
    result = audit_run(tmp_path, {'scenario_id': 'fixture', 'depth_raster_path': 'data/run/results/depth.tif',
                                  'execution_status': 'FAILED', 'exit_code': 1})
    assert not result['eligible_for_canonical_training']


@pytest.mark.parametrize('rain_time,mass,depth,expected', [(72000, [0, 0], 0., True),
                                                        (0, [0, 0], 0., False),
                                                        (72000, [0, 2], 0., False),
                                                        (72000, [0, 0], .5, False)])
def test_zero_depth_cause_needs_three_agreeing_evidence_streams(rain_time, mass, depth, expected):
    assert zero_depth_explained(first_rain_time_s=rain_time, sim_time_s=3600,
                                cumulative_rain_m3=np.asarray(mass), maximum_depth_m=depth) == expected


def test_duplicate_scenario_split_rejected(tmp_path):
    record = sample_record(tmp_path, 'same', 1., 'train')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'records': [record, {**record, 'split': 'validation'}], 'input_channels': ['x']}))
    with pytest.raises(ValueError, match='Unique scenario'):
        build_verified_dataset(tmp_path, manifest, tmp_path / 'out')


def test_raw_solver_tampering_rejected(tmp_path):
    record = sample_record(tmp_path, 's', 1., 'train')
    Path(record['raw_output_path']).write_text('changed')
    with pytest.raises(ValueError, match='Raw solver'):
        validate_sample(tmp_path, record)
