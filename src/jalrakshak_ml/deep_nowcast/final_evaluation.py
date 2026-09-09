"""Common, support-aware Phase 4E validation metrics and multi-seed aggregation."""

from __future__ import annotations

from typing import Any

import numpy as np

from .final_contracts import HORIZONS_MINUTES, SEEDS

THRESHOLDS_MM_H = (0.1, 1.0, 5.0, 10.0)


def _metrics(observed: np.ndarray, predicted: np.ndarray, threshold: float) -> dict[str, Any]:
    observed_positive = observed >= threshold
    predicted_positive = predicted >= threshold
    tp = int(np.count_nonzero(observed_positive & predicted_positive))
    fp = int(np.count_nonzero(~observed_positive & predicted_positive))
    fn = int(np.count_nonzero(observed_positive & ~predicted_positive))
    positive_count = int(np.count_nonzero(observed_positive))
    if positive_count < 20:
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "positive_target_count": positive_count,
            "valid_sample_count": int(observed.size),
            "pod": None,
            "far": None,
            "csi": None,
            "f1": None,
            "bias": None,
        }
    return {
        "status": "OK",
        "positive_target_count": positive_count,
        "valid_sample_count": int(observed.size),
        "pod": tp / (tp + fn) if tp + fn else None,
        "far": fp / (tp + fp) if tp + fp else None,
        "csi": tp / (tp + fp + fn) if tp + fp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "bias": (tp + fp) / (tp + fn) if tp + fn else None,
    }


def evaluate_validation_events(
    event_data: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
) -> dict[str, Any]:
    """Evaluate identical masked samples overall, by event, horizon and threshold."""
    per_event: dict[str, Any] = {}
    event_positive_support: dict[tuple[int, float], int] = {}
    for event_id, (prediction, target, mask) in event_data.items():
        if prediction.shape != target.shape or mask.shape != target.shape:
            raise ValueError("Prediction, target and mask shapes must match")
        if prediction.ndim != 5 or prediction.shape[1:3] != (4, 1):
            raise ValueError("Expected [N,4,1,H,W]")
        valid = mask.astype(bool) & np.isfinite(prediction) & np.isfinite(target)
        event_report: dict[str, Any] = {"horizons": {}}
        for horizon_index, minutes in enumerate(HORIZONS_MINUTES):
            horizon_valid = valid[:, horizon_index]
            observed = target[:, horizon_index][horizon_valid]
            predicted = prediction[:, horizon_index][horizon_valid]
            continuous = {
                "mae": float(np.mean(np.abs(predicted - observed))),
                "rmse": float(np.sqrt(np.mean((predicted - observed) ** 2))),
                "bias": float(np.mean(predicted - observed)),
                "valid_sample_count": int(observed.size),
            }
            thresholds = {}
            for threshold in THRESHOLDS_MM_H:
                thresholds[str(threshold)] = _metrics(observed, predicted, threshold)
                if np.count_nonzero(observed >= threshold):
                    key = (horizon_index, threshold)
                    event_positive_support[key] = event_positive_support.get(key, 0) + 1
            event_report["horizons"][str(minutes)] = {
                "continuous": continuous,
                "thresholds": thresholds,
            }
        per_event[event_id] = event_report

    combined: dict[str, Any] = {"horizons": {}}
    for horizon_index, minutes in enumerate(HORIZONS_MINUTES):
        obs_parts, pred_parts = [], []
        for prediction, target, mask in event_data.values():
            valid = mask[:, horizon_index].astype(bool)
            valid &= np.isfinite(prediction[:, horizon_index])
            valid &= np.isfinite(target[:, horizon_index])
            obs_parts.append(target[:, horizon_index][valid])
            pred_parts.append(prediction[:, horizon_index][valid])
        observed, predicted = np.concatenate(obs_parts), np.concatenate(pred_parts)
        threshold_reports = {}
        for threshold in THRESHOLDS_MM_H:
            report = _metrics(observed, predicted, threshold)
            report["supporting_event_count"] = event_positive_support.get(
                (horizon_index, threshold), 0
            )
            if report["supporting_event_count"] < 2:
                report.update(
                    status="INSUFFICIENT_SUPPORT",
                    pod=None,
                    far=None,
                    csi=None,
                    f1=None,
                    bias=None,
                )
            threshold_reports[str(threshold)] = report
        combined["horizons"][str(minutes)] = {
            "continuous": {
                "mae": float(np.mean(np.abs(predicted - observed))),
                "rmse": float(np.sqrt(np.mean((predicted - observed) ** 2))),
                "bias": float(np.mean(predicted - observed)),
                "valid_sample_count": int(observed.size),
            },
            "thresholds": threshold_reports,
        }
    return {"overall": combined, "per_event": per_event}


def paired_event_bootstrap(
    candidate_event_scores: dict[str, float],
    reference_event_scores: dict[str, float],
    *,
    seed: int = 26071,
    iterations: int = 2000,
) -> dict[str, Any]:
    """Bootstrap paired event-level score differences; pixels are never resampled."""
    if set(candidate_event_scores) != set(reference_event_scores):
        raise ValueError("Paired comparison requires the identical event set")
    if len(candidate_event_scores) < 2 or iterations < 1:
        raise ValueError("Paired event bootstrap requires at least two events and one iteration")
    event_ids = sorted(candidate_event_scores)
    differences = np.asarray(
        [candidate_event_scores[event] - reference_event_scores[event] for event in event_ids],
        dtype=float,
    )
    if not np.isfinite(differences).all():
        raise ValueError("Paired event scores must be finite")
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, differences.size, size=(iterations, differences.size))
    estimates = differences[sampled].mean(axis=1)
    return {
        "estimate_candidate_minus_reference": float(differences.mean()),
        "ci_low": float(np.percentile(estimates, 2.5)),
        "ci_high": float(np.percentile(estimates, 97.5)),
        "resampling_unit": "event",
        "number_of_bootstrap_units": len(event_ids),
        "event_ids": event_ids,
        "iterations": iterations,
        "seed": seed,
        "paired_common_samples": True,
        "pixel_independence_assumed": False,
    }


def aggregate_deep_seeds(seed_reports: dict[int, dict[str, float]]) -> dict[str, Any]:
    if set(seed_reports) != set(SEEDS):
        raise ValueError(f"Exactly the required seeds are required: {SEEDS}")
    metric_names = set.intersection(*(set(report) for report in seed_reports.values()))
    aggregate = {}
    for name in sorted(metric_names):
        values = np.asarray([seed_reports[seed][name] for seed in SEEDS], dtype=float)
        if np.isfinite(values).all():
            aggregate[name] = {
                "mean": float(values.mean()),
                "standard_deviation": float(values.std(ddof=1)),
            }
    return {
        "individual_seeds": {str(seed): seed_reports[seed] for seed in SEEDS},
        "aggregate": aggregate,
        "independence_unit": "seed_run; event identity retained upstream",
    }
