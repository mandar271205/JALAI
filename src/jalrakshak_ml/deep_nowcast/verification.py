"""Pooling helpers shared by training validation and held-out evaluation."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _aggregate(rows: list[dict[str, Any]], thresholds: list[float]) -> dict[str, Any]:
    valid = sum(int(row["valid_pixels"]) for row in rows)
    absolute_error = sum(float(row["absolute_error_sum"]) for row in rows)
    squared_error = sum(float(row["squared_error_sum"]) for row in rows)
    signed_error = sum(float(row["error_sum"]) for row in rows)
    output: dict[str, Any] = {
        "valid_pixels": valid,
        "mae": absolute_error / valid if valid else None,
        "rmse": math.sqrt(squared_error / valid) if valid else None,
        "bias": signed_error / valid if valid else None,
    }
    for threshold in thresholds:
        suffix = str(threshold)
        hits = sum(float(row[f"hits_{suffix}"]) for row in rows)
        misses = sum(float(row[f"misses_{suffix}"]) for row in rows)
        false_alarms = sum(float(row[f"false_alarms_{suffix}"]) for row in rows)
        correct_negatives = sum(float(row[f"correct_negatives_{suffix}"]) for row in rows)
        pod = _safe_ratio(hits, hits + misses)
        far = _safe_ratio(false_alarms, hits + false_alarms)
        csi = _safe_ratio(hits, hits + misses + false_alarms)
        precision = _safe_ratio(hits, hits + false_alarms)
        f1 = (
            2.0 * precision * pod / (precision + pod)
            if precision is not None and pod is not None and precision + pod
            else None
        )
        output.update({
            f"pod_{suffix}": pod,
            f"far_{suffix}": far,
            f"csi_{suffix}": csi,
            f"f1_{suffix}": f1,
            f"bias_{suffix}": _safe_ratio(hits + false_alarms, hits + misses),
            f"hits_{suffix}": int(hits),
            f"misses_{suffix}": int(misses),
            f"false_alarms_{suffix}": int(false_alarms),
            f"correct_negatives_{suffix}": int(correct_negatives),
        })
    return output


def pool_metric_rows(
    sample_rows: list[list[dict[str, Any]]],
    thresholds: list[float],
    *,
    temporal_step_minutes: int = 30,
) -> dict[str, Any]:
    """Pool errors and contingency counts over all valid space-time cells."""
    flattened = [row for sample in sample_rows for row in sample]
    if not flattened:
        return {"overall": {}, "by_lead": []}
    leads = sorted({int(row["lead_time"]) for row in flattened})
    by_lead = []
    for lead in leads:
        pooled = _aggregate(
            [row for row in flattened if int(row["lead_time"]) == lead],
            thresholds,
        )
        pooled["lead_time"] = lead
        pooled["horizon_minutes"] = lead * temporal_step_minutes
        by_lead.append(pooled)
    return {"overall": _aggregate(flattened, thresholds), "by_lead": by_lead}


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)
    return value
