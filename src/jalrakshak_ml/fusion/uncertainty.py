"""Uncertainty foundation metrics for multi-model ensemble nowcasting and NWP fusion.

Exposes ensemble spread, provider disagreement, agreement score, and confidence
without claiming uncalibrated probabilistic calibration.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def compute_ensemble_spread(
    forecasts: Sequence[np.ndarray],
    weights: Sequence[float] | None = None,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Compute (weighted) pixel-wise standard deviation across providers.

    Parameters
    ----------
    forecasts : sequence of [H, Y, X] arrays
    weights : sequence of weights of length len(forecasts)
    valid_mask : optional [H, Y, X] boolean mask

    Returns
    -------
    spread : [H, Y, X] array (std dev)
    """
    if not forecasts:
        raise ValueError("Cannot compute spread of empty ensemble")
    stack = np.stack(forecasts, axis=0)  # [M, H, Y, X]
    m, h, y, x = stack.shape
    if m == 1:
        return np.zeros((h, y, x), dtype=np.float32)

    if weights is None:
        spread = np.std(stack, axis=0, ddof=1 if m > 1 else 0)
    else:
        w = np.asarray(weights, dtype=np.float32)
        w = w / (w.sum() + 1e-8)
        w_expanded = w[:, None, None, None]
        mean = np.sum(stack * w_expanded, axis=0)
        variance = np.sum(w_expanded * ((stack - mean) ** 2), axis=0)
        spread = np.sqrt(np.maximum(0.0, variance))

    if valid_mask is not None:
        spread = np.where(valid_mask, spread, 0.0)
    return spread.astype(np.float32)


def compute_provider_disagreement(
    forecasts: dict[str, np.ndarray],
    valid_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute spatial disagreement metrics across providers per horizon.

    Returns
    -------
    dict with:
      - mean_pairwise_abs_diff: list of float per horizon
      - max_spread: list of float per horizon (spatial mean of max - min)
      - pairwise_correlations: dict of (p1, p2) -> list of float
    """
    names = list(forecasts.keys())
    m = len(names)
    if m < 2:
        h = next(iter(forecasts.values())).shape[0] if forecasts else 0
        return {
            "mean_pairwise_abs_diff": [0.0] * h,
            "max_spread": [0.0] * h,
            "pairwise_correlations": {},
        }

    h = forecasts[names[0]].shape[0]
    pairwise_diffs = []
    pairwise_corrs = {}

    for i in range(m):
        for j in range(i + 1, m):
            f1 = forecasts[names[i]]
            f2 = forecasts[names[j]]
            pair_key = f"{names[i]}_vs_{names[j]}"
            pair_diffs_h = []
            pair_corrs_h = []
            for lead in range(h):
                f1_lead = f1[lead]
                f2_lead = f2[lead]
                mask = valid_mask[lead] if valid_mask is not None else np.ones_like(f1_lead, dtype=bool)
                mask &= np.isfinite(f1_lead) & np.isfinite(f2_lead)
                if not np.any(mask):
                    pair_diffs_h.append(0.0)
                    pair_corrs_h.append(1.0)
                    continue
                v1 = f1_lead[mask]
                v2 = f2_lead[mask]
                diff = float(np.mean(np.abs(v1 - v2)))
                pair_diffs_h.append(diff)
                if np.std(v1) > 1e-4 and np.std(v2) > 1e-4:
                    corr = float(np.corrcoef(v1, v2)[0, 1])
                else:
                    corr = 1.0 if np.allclose(v1, v2, atol=1e-3) else 0.0
                pair_corrs_h.append(corr)
            pairwise_corrs[pair_key] = pair_corrs_h
            pairwise_diffs.append(pair_diffs_h)

    # Average pairwise diff per lead
    mean_pairwise = [
        float(np.mean([pair[lead] for pair in pairwise_diffs]))
        for lead in range(h)
    ]

    # Max - min spread per lead
    stack = np.stack([forecasts[name] for name in names], axis=0)  # [M, H, Y, X]
    max_min_spread = np.max(stack, axis=0) - np.min(stack, axis=0)  # [H, Y, X]
    mean_max_spread = [
        float(np.mean(max_min_spread[lead][valid_mask[lead]] if valid_mask is not None else max_min_spread[lead]))
        for lead in range(h)
    ]

    return {
        "mean_pairwise_abs_diff": mean_pairwise,
        "max_spread": mean_max_spread,
        "pairwise_correlations": pairwise_corrs,
    }


def compute_forecast_confidence(
    mean_forecast: np.ndarray,
    spread: np.ndarray,
    valid_count: int,
    expected_count: int = 3,
    data_quality: float = 1.0,
) -> dict[str, Any]:
    """Compute auditable agreement and confidence scores per horizon.

    Parameters
    ----------
    mean_forecast : [H, Y, X] ensemble mean
    spread : [H, Y, X] ensemble spread
    valid_count : number of valid providers used
    expected_count : target ensemble size
    data_quality : quality factor from input frames [0, 1]

    Returns
    -------
    dict with:
      - agreement_score: list of float per lead [0, 1]
      - confidence_score: list of float per lead [0, 1]
      - mean_spread_mm_h: list of float per lead
      - mean_rainfall_mm_h: list of float per lead
    """
    h = mean_forecast.shape[0]
    agreement_scores = []
    confidence_scores = []
    mean_spreads = []
    mean_rains = []

    provider_fraction = min(1.0, valid_count / max(1, expected_count))

    for lead in range(h):
        r_lead = mean_forecast[lead]
        s_lead = spread[lead]
        mean_r = float(np.mean(r_lead[np.isfinite(r_lead)])) if np.any(np.isfinite(r_lead)) else 0.0
        mean_s = float(np.mean(s_lead[np.isfinite(s_lead)])) if np.any(np.isfinite(s_lead)) else 0.0
        mean_rains.append(mean_r)
        mean_spreads.append(mean_s)

        # Agreement decays as spread increases relative to signal (or baseline 1 mm/h)
        scale = max(1.0, mean_r)
        agreement = float(np.exp(-mean_s / scale))
        agreement = float(np.clip(agreement, 0.0, 1.0))
        agreement_scores.append(agreement)

        conf = agreement * (0.5 + 0.5 * provider_fraction) * float(np.clip(data_quality, 0.0, 1.0))
        confidence_scores.append(float(np.clip(conf, 0.0, 1.0)))

    return {
        "agreement_score": agreement_scores,
        "confidence_score": confidence_scores,
        "mean_spread_mm_h": mean_spreads,
        "mean_rainfall_mm_h": mean_rains,
        "valid_providers_count": valid_count,
        "expected_providers_count": expected_count,
        "data_quality_factor": data_quality,
    }
