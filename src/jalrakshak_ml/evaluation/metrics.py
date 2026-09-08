"""Continuous, categorical, and probabilistic nowcast metrics."""
from __future__ import annotations

import numpy as np


def _valid_mask(
    obs: np.ndarray,
    pred: np.ndarray,
    valid_mask: np.ndarray | None,
) -> np.ndarray:
    if obs.shape != pred.shape:
        raise ValueError(f"Shape mismatch: obs {obs.shape} != pred {pred.shape}")
    valid = np.isfinite(obs) & np.isfinite(pred)
    if valid_mask is not None:
        if valid_mask.shape != obs.shape:
            raise ValueError("valid_mask must match observation shape")
        valid &= valid_mask.astype(bool)
    return valid


def compute_continuous_metrics(
    obs: np.ndarray,
    pred: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute MAE and RMSE over finite, explicitly valid cells."""
    valid = _valid_mask(obs, pred, valid_mask)
    if not np.any(valid):
        return {"mae": np.nan, "rmse": np.nan}
    difference = pred[valid] - obs[valid]
    return {
        "mae": float(np.mean(np.abs(difference))),
        "rmse": float(np.sqrt(np.mean(difference**2))),
    }


def compute_dichotomous_metrics(
    obs: np.ndarray,
    pred: np.ndarray,
    threshold: float,
    valid_mask: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute categorical metrics and raw counts over explicitly valid cells."""
    valid = _valid_mask(obs, pred, valid_mask)
    if not np.any(valid):
        return {
            "csi": np.nan,
            "far": np.nan,
            "pod": np.nan,
            "f1": np.nan,
            "bias": np.nan,
            "hits": 0.0,
            "misses": 0.0,
            "false_alarms": 0.0,
            "correct_negatives": 0.0,
        }

    observed = obs[valid] >= threshold
    predicted = pred[valid] >= threshold
    hits = np.sum(observed & predicted)
    misses = np.sum(observed & ~predicted)
    false_alarms = np.sum(~observed & predicted)
    correct_negatives = np.sum(~observed & ~predicted)

    pod = hits / (hits + misses) if hits + misses else np.nan
    far = false_alarms / (hits + false_alarms) if hits + false_alarms else np.nan
    csi = hits / (hits + misses + false_alarms) if hits + misses + false_alarms else np.nan
    bias = (hits + false_alarms) / (hits + misses) if hits + misses else np.nan
    precision = 1.0 - far if np.isfinite(far) else np.nan
    f1 = (
        2.0 * precision * pod / (precision + pod)
        if np.isfinite(precision) and np.isfinite(pod) and precision + pod
        else np.nan
    )
    return {
        "pod": float(pod),
        "far": float(far),
        "csi": float(csi),
        "f1": float(f1),
        "bias": float(bias),
        "hits": float(hits),
        "misses": float(misses),
        "false_alarms": float(false_alarms),
        "correct_negatives": float(correct_negatives),
    }


def compute_probabilistic_metrics(
    obs: np.ndarray,
    prob_pred: np.ndarray,
    threshold: float,
    valid_mask: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute Brier score and binned reliability over explicitly valid cells."""
    valid = _valid_mask(obs, prob_pred, valid_mask)
    if not np.any(valid):
        return {"brier_score": np.nan, "reliability": np.nan}
    observed = obs[valid] >= threshold
    probability = prob_pred[valid]
    brier_score = float(np.mean((probability - observed.astype(float)) ** 2))
    bins = np.linspace(0, 1, 11)
    bin_indices = np.clip(np.digitize(probability, bins) - 1, 0, 9)
    reliability = 0.0
    count = len(probability)
    for index in range(10):
        selected = bin_indices == index
        bin_count = np.sum(selected)
        if bin_count:
            forecast_frequency = np.mean(probability[selected])
            observed_frequency = np.mean(observed[selected])
            reliability += (bin_count / count) * (
                (forecast_frequency - observed_frequency) ** 2
            )
    return {"brier_score": brier_score, "reliability": float(reliability)}
