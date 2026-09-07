import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from .metrics import compute_continuous_metrics, compute_dichotomous_metrics, compute_probabilistic_metrics

class NowcastEvaluator:
    """
    Evaluator class for nowcasting models.
    Computes metrics across specified lead times.
    """

    def __init__(self, thresholds: List[float] = [0.1, 1.0, 5.0]):
        """
        Args:
            thresholds: List of thresholds for dichotomous metrics (e.g., rainfall intensities).
        """
        self.thresholds = thresholds

    def evaluate_sequence(self, obs: np.ndarray, pred: np.ndarray, prob_pred: Optional[np.ndarray] = None) -> pd.DataFrame:
        """
        Evaluates a predicted sequence against an observed sequence.

        Args:
            obs: 3D array of ground truth (lead_time, height, width).
            pred: 3D array of predictions (lead_time, height, width).
            prob_pred: Optional 3D array of probabilistic predictions [0, 1] (lead_time, height, width).

        Returns:
            pd.DataFrame: A DataFrame where each row corresponds to a lead time
                          and columns contain metrics.
        """
        if obs.ndim != 3 or pred.ndim != 3:
            raise ValueError(f"Expected 3D arrays (time, y, x). Got obs {obs.ndim}D, pred {pred.ndim}D.")
        if obs.shape != pred.shape:
            raise ValueError(f"Shape mismatch: obs {obs.shape} != pred {pred.shape}")
        if prob_pred is not None and prob_pred.shape != obs.shape:
            raise ValueError(f"Shape mismatch: obs {obs.shape} != prob_pred {prob_pred.shape}")

        lead_times = obs.shape[0]
        results = []

        for t in range(lead_times):
            obs_t = obs[t]
            pred_t = pred[t]
            
            # Continuous metrics
            row_metrics = compute_continuous_metrics(obs_t, pred_t)
            row_metrics["lead_time"] = t + 1
            
            # Dichotomous and Probabilistic metrics per threshold
            for thresh in self.thresholds:
                thresh_metrics = compute_dichotomous_metrics(obs_t, pred_t, threshold=thresh)
                for k, v in thresh_metrics.items():
                    row_metrics[f"{k}_{thresh}"] = v
                    
                if prob_pred is not None:
                    prob_metrics = compute_probabilistic_metrics(obs_t, prob_pred[t], threshold=thresh)
                    for k, v in prob_metrics.items():
                        row_metrics[f"{k}_{thresh}"] = v
            
            results.append(row_metrics)
            
        # Reorder columns to put lead_time first
        df = pd.DataFrame(results)
        cols = ["lead_time"] + [c for c in df.columns if c != "lead_time"]
        return df[cols]

