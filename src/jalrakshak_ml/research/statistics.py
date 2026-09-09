"""Block-aware statistical comparison utilities."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def paired_block_bootstrap(
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    unit: str,
    n_resamples: int = 5000,
    seed: int = 42,
) -> dict[str, float | int | str | list[float]]:
    if unit not in {"event", "scenario"}:
        raise ValueError("Independent bootstrap unit must be event or scenario, never pixel")
    a = np.asarray(baseline, dtype=float)
    b = np.asarray(candidate, dtype=float)
    if a.shape != b.shape or a.ndim != 1 or len(a) < 2:
        raise ValueError("Paired comparisons require at least two matching independent blocks")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("Bootstrap inputs must be finite")
    differences = b - a
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(a), size=(n_resamples, len(a)))
    means = differences[indices].mean(axis=1)
    return {
        "unit": unit,
        "independent_blocks": len(a),
        "mean_difference": float(differences.mean()),
        "median_difference": float(np.median(differences)),
        "ci95": [float(x) for x in np.quantile(means, [0.025, 0.975])],
        "win_probability": float(np.mean(means > 0)),
        "n_resamples": n_resamples,
    }
