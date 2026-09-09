"""Uncertainty propagation across rainfall, hazard, flood, and risk dimensions.

Enforces scenario/ensemble level uncertainty; strictly prohibits independent-pixel bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class UncertaintyField:
    mean: np.ndarray
    standard_deviation: np.ndarray
    quantiles: dict[str, np.ndarray]  # e.g. "p10", "p50", "p90"
    scenario_count: int
    probability_calibrated: bool
    source_dimension: str  # rainfall, hazard, flood_depth, risk
    provenance: dict[str, Any]

    def validate(self) -> None:
        if self.mean.shape != self.standard_deviation.shape:
            raise ValueError("Mean and standard deviation shape mismatch")
        if not np.isfinite(self.mean).all() or not np.isfinite(self.standard_deviation).all():
            raise ValueError("Uncertainty fields contain non-finite numbers")
        if (self.standard_deviation < 0).any():
            raise ValueError("Standard deviation cannot be negative")
        for q_name, q_arr in self.quantiles.items():
            if q_arr.shape != self.mean.shape:
                raise ValueError(f"Quantile {q_name} shape mismatch")


class UncertaintyPropagator:
    """Propagate scenario ensembles without independent pixel bootstrap."""

    @staticmethod
    def propagate_ensemble(
        ensemble_grids: list[np.ndarray],
        weights: list[float] | None = None,
        *,
        dimension: str = "risk",
        calibrated: bool = False,
        provenance: dict[str, Any] | None = None,
    ) -> UncertaintyField:
        if not ensemble_grids:
            raise ValueError("Ensemble must contain at least one grid")
        shape = ensemble_grids[0].shape
        for g in ensemble_grids:
            if g.shape != shape:
                raise ValueError("All ensemble members must share grid shape")
            if not np.isfinite(g).all():
                raise ValueError("Ensemble grid contains NaN or Inf")

        n = len(ensemble_grids)
        w = np.ones(n, dtype=np.float64) / n if weights is None else np.asarray(weights, dtype=np.float64)
        if (w < 0).any() or not np.isclose(w.sum(), 1.0):
            raise ValueError("Weights must be nonnegative and sum to 1.0")

        stack = np.stack(ensemble_grids, axis=0).astype(np.float64)  # (N, H, W)
        mean = np.tensordot(w, stack, axes=(0, 0))
        var = np.tensordot(w, (stack - mean) ** 2, axes=(0, 0))
        std = np.sqrt(np.maximum(0.0, var))

        # Quantiles (weighted or unweighted percentiles along scenario axis)
        p10 = np.percentile(stack, 10, axis=0)
        p50 = np.percentile(stack, 50, axis=0)
        p90 = np.percentile(stack, 90, axis=0)

        return UncertaintyField(
            mean=mean.astype(np.float32),
            standard_deviation=std.astype(np.float32),
            quantiles={
                "p10": p10.astype(np.float32),
                "p50": p50.astype(np.float32),
                "p90": p90.astype(np.float32),
            },
            scenario_count=n,
            probability_calibrated=calibrated,
            source_dimension=dimension,
            provenance=provenance or {"method": "weighted_scenario_ensemble"},
        )

    @staticmethod
    def compute_exceedance_probability(
        ensemble_grids: list[np.ndarray],
        threshold: float,
        weights: list[float] | None = None,
    ) -> np.ndarray:
        """Compute probability of exceeding threshold: P(X >= threshold)."""
        if not ensemble_grids:
            raise ValueError("Empty ensemble")
        n = len(ensemble_grids)
        w = np.ones(n, dtype=np.float64) / n if weights is None else np.asarray(weights, dtype=np.float64)
        stack = np.stack(ensemble_grids, axis=0) >= threshold  # (N, H, W) bool
        prob = np.tensordot(w, stack.astype(np.float64), axes=(0, 0))
        return np.clip(prob, 0.0, 1.0).astype(np.float32)
