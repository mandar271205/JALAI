"""Lead-time nowcast evaluator with explicit validity-mask support."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import (
    compute_continuous_metrics,
    compute_dichotomous_metrics,
    compute_probabilistic_metrics,
)


class NowcastEvaluator:
    """Compute continuous and threshold metrics for nowcast sequences."""

    def __init__(self, thresholds: list[float] | None = None):
        self.thresholds = thresholds or [0.1, 1.0, 5.0]

    def evaluate_sequence(
        self,
        obs: np.ndarray,
        pred: np.ndarray,
        prob_pred: np.ndarray | None = None,
        valid_mask: np.ndarray | None = None,
    ) -> pd.DataFrame:
        """Evaluate ``[lead_time, height, width]`` arrays over valid cells."""
        if obs.ndim != 3 or pred.ndim != 3:
            raise ValueError(
                f"Expected 3D arrays (time, y, x). Got obs {obs.ndim}D, pred {pred.ndim}D."
            )
        if obs.shape != pred.shape:
            raise ValueError(f"Shape mismatch: obs {obs.shape} != pred {pred.shape}")
        if prob_pred is not None and prob_pred.shape != obs.shape:
            raise ValueError(f"Shape mismatch: obs {obs.shape} != prob_pred {prob_pred.shape}")
        if valid_mask is not None and valid_mask.shape != obs.shape:
            raise ValueError(f"Shape mismatch: obs {obs.shape} != valid_mask {valid_mask.shape}")

        results = []
        for index in range(obs.shape[0]):
            observation = obs[index]
            prediction = pred[index]
            mask = valid_mask[index] if valid_mask is not None else None
            effective = np.isfinite(observation) & np.isfinite(prediction)
            if mask is not None:
                effective &= mask.astype(bool)
            error = np.where(effective, prediction - observation, 0.0)
            row_metrics = compute_continuous_metrics(observation, prediction, mask)
            row_metrics.update({
                "lead_time": index + 1,
                "valid_pixels": int(effective.sum()),
                "error_sum": float(error.sum()),
                "absolute_error_sum": float(np.abs(error).sum()),
                "squared_error_sum": float(np.square(error).sum()),
            })
            for threshold in self.thresholds:
                categorical = compute_dichotomous_metrics(
                    observation,
                    prediction,
                    threshold=threshold,
                    valid_mask=mask,
                )
                for name, value in categorical.items():
                    row_metrics[f"{name}_{threshold}"] = value
                if prob_pred is not None:
                    probabilistic = compute_probabilistic_metrics(
                        observation,
                        prob_pred[index],
                        threshold=threshold,
                        valid_mask=mask,
                    )
                    for name, value in probabilistic.items():
                        row_metrics[f"{name}_{threshold}"] = value
            results.append(row_metrics)

        frame = pd.DataFrame(results)
        columns = ["lead_time"] + [column for column in frame.columns if column != "lead_time"]
        return frame[columns]
