from __future__ import annotations

import numpy as np


DEFAULT_WEIGHTS = {
    "completeness": 0.25,
    "freshness": 0.20,
    "range_validity": 0.20,
    "spatial_coverage": 0.20,
    "source_specific_qc": 0.15,
}


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def compute_quality_score(
    *,
    completeness: float,
    freshness: float,
    range_validity: float,
    spatial_coverage: float,
    source_specific_qc: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Data quality only. This is intentionally NOT model/forecast confidence."""
    weights = weights or DEFAULT_WEIGHTS
    values = {
        "completeness": _clip01(completeness),
        "freshness": _clip01(freshness),
        "range_validity": _clip01(range_validity),
        "spatial_coverage": _clip01(spatial_coverage),
        "source_specific_qc": _clip01(source_specific_qc),
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Quality weights must sum to > 0.")
    return round(sum(values[k] * weights[k] for k in values) / total_weight, 6)


def precipitation_qc(array: np.ndarray, max_reasonable_mm_h: float = 300.0) -> dict:
    arr = np.asarray(array, dtype="float32")
    finite = np.isfinite(arr)
    total = arr.size
    valid_count = int(finite.sum())

    if total == 0:
        raise ValueError("Empty precipitation array.")

    completeness = valid_count / total
    missing_percent = 100.0 * (1.0 - completeness)

    valid_values = arr[finite]
    if valid_values.size:
        in_range = (valid_values >= 0.0) & (valid_values <= max_reasonable_mm_h)
        range_validity = float(in_range.mean())
    else:
        range_validity = 0.0

    impossible_mask = finite & ((arr < 0.0) | (arr > max_reasonable_mm_h))

    return {
        "completeness": float(completeness),
        "missing_percent": float(missing_percent),
        "range_validity": range_validity,
        "impossible_count": int(impossible_mask.sum()),
        "no_data_mask": ~finite,
    }
