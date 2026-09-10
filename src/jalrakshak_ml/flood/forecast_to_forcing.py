"""Explicit forecast-to-forcing interface; never selects or opens rainfall models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from pyproj import CRS


@dataclass(frozen=True)
class GridSpec:
    crs: str
    shape: tuple[int, int]
    transform: tuple[float, ...]

    def validate(self):
        CRS.from_user_input(self.crs)
        if len(self.shape) != 2 or min(self.shape) <= 0 or len(self.transform) != 6:
            raise ValueError('Invalid grid metadata')
        a, b, _, d, e, _ = self.transform
        if not np.isfinite(self.transform).all() or a <= 0 or e >= 0 or b or d:
            raise ValueError('Finite north-up grid required')


def interval_nodes(rates: np.ndarray, cadence_s: float = 1800.) -> tuple[np.ndarray, np.ndarray]:
    """Encode interval means as near-steps for a linearly interpolating solver.

    Symmetric 2-microsecond ramps conserve whole-event accumulation exactly;
    per-interval differences are bounded and reported, not new rainfall information.
    """
    rates = np.asarray(rates, dtype=float)
    if rates.ndim != 1 or not rates.size or not np.isfinite(rates).all() or (rates < 0).any():
        raise ValueError('Finite nonnegative interval rates required')
    if cadence_s <= 0:
        raise ValueError('Positive cadence required')
    times, values = [0.], [rates[0]]
    for i in range(1, len(rates)):
        times.extend([i * cadence_s - 1e-6, i * cadence_s + 1e-6])
        values.extend([rates[i - 1], rates[i]])
    times.append(len(rates) * cadence_s)
    values.append(rates[-1])
    return np.asarray(values), np.asarray(times)


def write_interval_rain(path: Path, rates: np.ndarray) -> dict:
    if path.exists():
        raise FileExistsError(path)
    values, times = interval_nodes(rates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('# Interval forcing; rates mm/h, times seconds\n'
                    + f'{len(values)} seconds\n'
                    + ''.join(f'{v:.10f}\t{t:.10f}\n' for v, t in zip(values, times, strict=True)))
    depth = float(np.sum((values[1:] + values[:-1]) * np.diff(times) / 2) / 3600)
    if not np.isclose(depth, np.sum(rates) / 2, atol=1e-8):
        raise ValueError('Forcing accumulation not conserved')
    return {'accumulation_mm': depth, 'encoding': 'piecewise_constant_with_symmetric_2us_ramps',
            'per_interval_rounding_bound_mm': float(np.max(values) * 2e-6 / 3600),
            'native_cadence_minutes': 30, 'independent_subinterval_information': False}


def forecast_to_forcing(*, issue_time: str, horizons_minutes: tuple[int, ...], values: np.ndarray,
                        valid_mask: np.ndarray, units: str, quantity: str, grid: GridSpec,
                        target_grid: GridSpec, model_version: str, data_version: str,
                        providers: tuple[str, ...], quality: float, confidence: float | None,
                        scenario_ids: tuple[str, ...], scenario_weights: tuple[float, ...],
                        source_type: str = 'forecast_model_output',
                        exceedance_probabilities: dict[float, np.ndarray] | None = None) -> dict:
    grid.validate()
    target_grid.validate()
    issue = datetime.fromisoformat(issue_time)
    if issue.tzinfo is None or horizons_minutes != (30, 60, 90, 120):
        raise ValueError('Timezone-aware issue time and exact four half-hour horizons required')
    if source_type != 'forecast_model_output':
        raise ValueError('This adapter accepts forecast_model_output, never observed or generated data')
    if grid != target_grid:
        raise ValueError('Grid mismatch: explicitly align before forcing conversion')
    if not model_version or not data_version or not providers:
        raise ValueError('Model/data/provider provenance required')
    if not 0 <= quality <= 1 or (confidence is not None and not 0 <= confidence <= 1):
        raise ValueError('Quality and confidence must be separate bounded values')
    array, mask = np.asarray(values, dtype=float), np.asarray(valid_mask, dtype=bool)
    expected = (len(scenario_ids), 4, *grid.shape)
    if array.shape != expected or mask.shape != expected or len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError('Unique scenarios and aligned [scenario,4,H,W] fields required')
    if not mask.all():
        raise ValueError('Unavailable rainfall cells: uniform full-domain forcing blocked; no imputation')
    if not np.isfinite(array).all() or (array < 0).any():
        raise ValueError('Rainfall must be finite and nonnegative')
    if (units, quantity) == ('mm/h', 'interval_mean_rate'):
        rate = array
    elif (units, quantity) == ('mm', 'interval_accumulation'):
        rate = array * 2
    else:
        raise ValueError('Use mm/h interval_mean_rate or mm interval_accumulation; cumulative is ambiguous')
    weights = np.asarray(scenario_weights)
    if weights.shape != (len(scenario_ids),) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('Nonnegative scenario weights must sum to one')
    for threshold, probability in (exceedance_probabilities or {}).items():
        if threshold < 0 or probability.shape != expected or not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
            raise ValueError('Invalid exceedance field')
    # Projected regular cells have equal area. Geographic grids need explicit area weighting.
    if not CRS.from_user_input(grid.crs).is_projected:
        raise ValueError('Projected equal-area cell weighting required for uniform domain forcing')
    means = rate.mean(axis=(-2, -1))
    return {'source_type': source_type, 'observed': False, 'model_version': model_version,
            'data_version': data_version, 'providers': list(providers), 'quality': quality,
            'confidence': confidence, 'issue_time': issue_time,
            'target_times': [(issue + timedelta(minutes=m)).isoformat() for m in horizons_minutes],
            'grid': grid.__dict__, 'scenario_ids': list(scenario_ids), 'weights': weights.tolist(),
            'rates_mm_h': means, 'accumulations_mm': means * .5,
            'spatial_method': 'uniform_domain_mean; spatial detail discarded explicitly',
            'uncertainty_semantics': 'scenario weights, not calibrated probabilities',
            'exceedance_probabilities_used_to_invent_scenarios': False,
            'rain_forecast_winner_selected': False}
