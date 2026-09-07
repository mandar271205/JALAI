import numpy as np
from typing import Dict

def compute_continuous_metrics(obs: np.ndarray, pred: np.ndarray) -> Dict[str, float]:
    """
    Computes continuous error metrics (MAE, RMSE).
    Handles NaNs in the inputs.

    Args:
        obs: Ground truth observations (any shape).
        pred: Predictions (must match obs shape).

    Returns:
        Dict with 'mae' and 'rmse' keys.
    """
    if obs.shape != pred.shape:
        raise ValueError(f"Shape mismatch: obs {obs.shape} != pred {pred.shape}")

    # Mask valid data (where both are not NaN)
    valid_mask = ~np.isnan(obs) & ~np.isnan(pred)
    if not np.any(valid_mask):
        return {"mae": np.nan, "rmse": np.nan}

    obs_v = obs[valid_mask]
    pred_v = pred[valid_mask]

    diff = pred_v - obs_v
    mae = float(np.mean(np.abs(diff)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))

    return {"mae": mae, "rmse": rmse}


def compute_dichotomous_metrics(obs: np.ndarray, pred: np.ndarray, threshold: float) -> Dict[str, float]:
    """
    Computes binary threshold-based metrics (CSI, FAR, POD, Bias).
    Handles NaNs in the inputs.

    Args:
        obs: Ground truth observations (any shape).
        pred: Predictions (must match obs shape).
        threshold: The threshold to binarize continuous values (e.g., rainfall > 0.1 mm/h).

    Returns:
        Dict with keys: 'csi' (Critical Success Index), 'far' (False Alarm Ratio), 
        'pod' (Probability of Detection), 'bias' (Frequency Bias).
    """
    if obs.shape != pred.shape:
        raise ValueError(f"Shape mismatch: obs {obs.shape} != pred {pred.shape}")

    # Mask valid data
    valid_mask = ~np.isnan(obs) & ~np.isnan(pred)
    if not np.any(valid_mask):
        return {"csi": np.nan, "far": np.nan, "pod": np.nan, "bias": np.nan}

    obs_v = obs[valid_mask] >= threshold
    pred_v = pred[valid_mask] >= threshold

    hits = np.sum(obs_v & pred_v)
    misses = np.sum(obs_v & ~pred_v)
    false_alarms = np.sum(~obs_v & pred_v)
    correct_negatives = np.sum(~obs_v & ~pred_v)
    
    pod = hits / (hits + misses) if (hits + misses) > 0 else np.nan
    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan
    csi = hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan
    bias = (hits + false_alarms) / (hits + misses) if (hits + misses) > 0 else np.nan
    
    # F1 Score = 2 * (Precision * Recall) / (Precision + Recall)
    # Where Precision = (1 - FAR) and Recall = POD
    precision = 1.0 - far if not np.isnan(far) else np.nan
    f1 = 2 * (precision * pod) / (precision + pod) if not np.isnan(precision) and not np.isnan(pod) and (precision + pod) > 0 else np.nan

    return {
        "pod": float(pod),
        "far": float(far),
        "csi": float(csi),
        "f1": float(f1),
        "bias": float(bias),
        "hits": float(hits),
        "misses": float(misses),
        "false_alarms": float(false_alarms),
        "correct_negatives": float(correct_negatives)
    }

def compute_probabilistic_metrics(obs: np.ndarray, prob_pred: np.ndarray, threshold: float) -> Dict[str, float]:
    """
    Computes probabilistic error metrics (Brier Score, Reliability).

    Args:
        obs: Ground truth observations (any shape).
        prob_pred: Predicted probabilities [0, 1] (must match obs shape).
        threshold: The threshold to binarize continuous observations.

    Returns:
        Dict with keys: 'brier_score', 'reliability'
    """
    if obs.shape != prob_pred.shape:
        raise ValueError(f"Shape mismatch: obs {obs.shape} != prob_pred {prob_pred.shape}")

    valid_mask = ~np.isnan(obs) & ~np.isnan(prob_pred)
    if not np.any(valid_mask):
        return {"brier_score": np.nan, "reliability": np.nan}

    obs_v = obs[valid_mask] >= threshold
    prob_v = prob_pred[valid_mask]

    # Brier Score = Mean Squared Error of probabilities vs binary targets
    brier_score = float(np.mean((prob_v - obs_v.astype(float)) ** 2))
    
    # Reliability computation (Brier Score Reliability component)
    # Bin probabilities into 10 decile bins
    bins = np.linspace(0, 1, 11)
    bin_indices = np.digitize(prob_v, bins) - 1
    bin_indices = np.clip(bin_indices, 0, 9) # 1.0 goes into bin 9
    
    reliability = 0.0
    N = len(prob_v)
    for k in range(10):
        mask_k = (bin_indices == k)
        n_k = np.sum(mask_k)
        if n_k > 0:
            p_k = np.mean(prob_v[mask_k])
            o_k = np.mean(obs_v[mask_k])
            reliability += (n_k / N) * ((p_k - o_k) ** 2)

    return {
        "brier_score": brier_score,
        "reliability": float(reliability)
    }
