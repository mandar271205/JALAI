"""Typed H x E x V risk, scenario uncertainty and exact local decompositions."""
from __future__ import annotations

import numpy as np

HAZARD_UNITS = {'susceptibility': 'relative_index', 'lisflood_simulated_depth': 'm',
                'fno_simulated_depth': 'm'}


def evaluate_risk(hazard: np.ndarray, exposure: np.ndarray, vulnerability: np.ndarray,
                  mask: np.ndarray, *, hazard_type: str, units: str, hazard_scale: float,
                  provenance: dict, quality: float, confidence: float | None) -> dict:
    if hazard_type not in HAZARD_UNITS or units != HAZARD_UNITS[hazard_type]:
        raise ValueError('Hazard type and units must agree; susceptibility is never depth')
    if not provenance or any(not provenance.get(k) for k in ('hazard', 'exposure', 'vulnerability')):
        raise ValueError('Provenance required for each component')
    if not np.isfinite(hazard_scale) or hazard_scale <= 0 or not 0 <= quality <= 1 or (confidence is not None and not 0 <= confidence <= 1):
        raise ValueError('Invalid scale/quality/confidence')
    if any(a.shape != hazard.shape for a in (exposure, vulnerability, mask)) or mask.dtype != bool:
        raise ValueError('Risk component/mask grid mismatch')
    if any(not np.isfinite(a[mask]).all() for a in (hazard, exposure, vulnerability)):
        raise ValueError('Non-finite supported risk component')
    if (hazard[mask] < 0).any() or any(((a[mask] < 0) | (a[mask] > 1)).any() for a in (exposure, vulnerability)):
        raise ValueError('Invalid component range')
    if hazard_type == 'susceptibility' and (hazard[mask] > 1).any():
        raise ValueError('Susceptibility must be bounded')
    h = np.clip(hazard / hazard_scale, 0, 1)
    risk = np.where(mask, h * exposure * vulnerability, np.nan)
    classes = np.full(hazard.shape, 'NODATA', dtype='<U8')
    categories = np.asarray(['LOW', 'MODERATE', 'HIGH', 'SEVERE'])
    classes[mask] = categories[np.digitize(risk[mask], [.2, .5, .8])]
    return {'risk_score': risk, 'risk_class': classes, 'valid_mask': mask.copy(),
            'hazard_type': hazard_type, 'hazard_units': units, 'components': {'hazard': h,
            'exposure': exposure.copy(), 'vulnerability': vulnerability.copy()}, 'quality': quality,
            'confidence': confidence, 'provenance': provenance, 'version': 'phase11_hev_v1',
            'calibrated_loss_or_damage': False, 'evidence_completeness': float(mask.mean()),
            'missing_data': {'invalid_cells': int((~mask).sum()), 'osm_coverage_unknown': True}}


def scenario_uncertainty(results: list[dict], weights: np.ndarray) -> dict:
    if not results or len(results) != len(weights) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('Valid scenario weights required')
    if len({r['hazard_type'] for r in results}) != 1:
        raise ValueError('Cannot mix susceptibility and simulated depth scenarios')
    shape = results[0]['risk_score'].shape
    if any(r['risk_score'].shape != shape for r in results):
        raise ValueError('Scenario grid mismatch')
    mask = np.logical_and.reduce([r['valid_mask'] for r in results])
    stack = np.stack([np.where(mask, r['risk_score'], 0.) for r in results])
    mean = np.sum(weights[:, None, None] * stack, axis=0)
    spread = np.sqrt(np.sum(weights[:, None, None] * (stack - mean) ** 2, axis=0))
    order = np.argsort(stack, axis=0)
    sorted_values = np.take_along_axis(stack, order, axis=0)
    cumulative = np.cumsum(np.take_along_axis(np.broadcast_to(weights[:, None, None], stack.shape), order, axis=0), axis=0)
    quantiles = {}
    for name, q in [('lower', .1), ('median', .5), ('upper', .9)]:
        index = np.argmax(cumulative >= q, axis=0)[None]
        quantiles[name] = np.where(mask, np.take_along_axis(sorted_values, index, axis=0)[0], np.nan)
    frequencies = {name: np.where(mask, np.sum(weights[:, None, None] * np.stack([r['risk_class'] == name for r in results]), axis=0), np.nan)
                   for name in ('LOW', 'MODERATE', 'HIGH', 'SEVERE')}
    return {'expected_risk': np.where(mask, mean, np.nan), **quantiles,
            'spread': np.where(mask, spread, np.nan), 'class_scenario_frequency': frequencies,
            'scenario_count': len(results), 'calibrated_probability': False,
            'confidence': None, 'uncertainty_score': np.where(mask, np.clip(spread * 2, 0, 1), np.nan),
            'meaning': 'weighted scenario distribution, not predictive confidence interval',
            'missing_source_uncertainty': 'not quantified; coverage and masks retained separately'}


def explain_cell(result: dict, row: int, col: int) -> dict:
    if not result['valid_mask'][row, col]:
        return {'status': 'INSUFFICIENT_EVIDENCE', 'factors': [], 'recommendations': ['consider field verification']}
    components = {k: float(v[row, col]) for k, v in result['components'].items()}
    risk = float(result['risk_score'][row, col])
    factors = [{'factor': key, 'value': value, 'direction': 'increases_risk',
                'contribution': risk / 3, 'evidence_source': result['provenance'][key],
                'confidence': result['confidence']} for key, value in components.items()]
    return {'status': 'EXPLAINED', 'risk_score': risk, 'hazard_type': result['hazard_type'],
            'factors': factors, 'contribution_method': 'zero-baseline Shapley of three-way product; equal risk/3 allocation',
            'components': components, 'missing_evidence': result['missing_data'],
            'recommendations': ['prioritize monitoring' if risk >= .2 else 'consider field verification'],
            'causal_or_calibrated_damage_claim': False}
