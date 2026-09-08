"""Probabilistic rainfall forecasting and validation-only calibration for JalRakshak AI.

Generates calibrated exceedance probabilities:
- P(rainfall > 0.1 mm/h)
- P(rainfall > 1.0 mm/h)
- P(rainfall > 5.0 mm/h)
- P(rainfall > 10.0 mm/h)

Includes:
- Empirical multi-provider ensemble exceedance
- Strict Validation-split probability calibration (Isotonic Regression)
- Strict support checks (insufficient_support when positive/negative count < 50)
- Monotonic threshold ordering enforcement: P(>0.1) >= P(>1.0) >= P(>5.0) >= P(>10.0)
- Brier Score, Brier Skill Score, ROC-AUC, PR-AUC, ECE, and reliability diagram bins
- ZERO held-out test data access during calibration or threshold selection
"""
from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from jalrakshak_ml.fusion.contracts import ForecastResult, _ensure_utc


@dataclass(slots=True)
class ProbabilisticForecastResult:
    """Standardized probabilistic nowcast result envelope."""

    expected_rainfall_mm_h: np.ndarray  # [H, Y, X]
    exceedance_probabilities: dict[float, np.ndarray]  # threshold -> [H, Y, X]
    probability_thresholds_mm_h: list[float]
    horizons_min: list[int]
    issue_time: datetime
    valid_mask: np.ndarray  # [H, Y, X]
    ensemble_spread: np.ndarray  # [H, Y, X]
    provider_disagreement: np.ndarray  # [H, Y, X]
    forecast_confidence: np.ndarray  # [H]
    calibration_status: dict[str, str]  # "{horizon}_{threshold}" -> status
    model_version: str = "probabilistic_nowcast_v1"
    calibration_version: str = "isotonic_validation_v1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.expected_rainfall_mm_h = np.asarray(self.expected_rainfall_mm_h, dtype=np.float32)
        h, y, x = self.expected_rainfall_mm_h.shape
        if len(self.horizons_min) != h:
            raise ValueError(f"Horizons count {len(self.horizons_min)} does not match shape {h}")

        for thr, prob in self.exceedance_probabilities.items():
            if prob.shape != (h, y, x):
                raise ValueError(f"Probability array for thr={thr} has shape {prob.shape}, expected {(h, y, x)}")
            # Strict [0, 1] range validation
            finite_p = prob[np.isfinite(prob)]
            if finite_p.size:
                if np.any(finite_p < -1e-5) or np.any(finite_p > 1.0 + 1e-5):
                    raise ValueError(f"Exceedance probability for thr={thr} out of [0, 1] bounds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "calibration_version": self.calibration_version,
            "issue_time": self.issue_time.isoformat(),
            "horizons_min": self.horizons_min,
            "thresholds_mm_h": self.probability_thresholds_mm_h,
            "shape": list(self.expected_rainfall_mm_h.shape),
            "calibration_status": self.calibration_status,
            "mean_spread_by_lead": [float(np.nanmean(self.ensemble_spread[i])) for i in range(len(self.horizons_min))],
            "metadata": self.metadata,
        }


class CalibratedProbabilisticNowcaster:
    """Generates calibrated probability forecasts from multi-provider ensemble predictions."""

    def __init__(
        self,
        thresholds: Sequence[float] = (0.1, 1.0, 5.0, 10.0),
        horizons_min: Sequence[int] = (30, 60, 90, 120),
        min_support_count: int = 50,
        logistic_steepness: float = 2.0,
        model_version: str = "probabilistic_nowcast_v1",
        calibration_version: str = "isotonic_validation_v1",
    ) -> None:
        self.thresholds = sorted(list(thresholds))
        self.horizons_min = list(horizons_min)
        self.min_support_count = min_support_count
        self.k = logistic_steepness
        self.model_version = model_version
        self.calibration_version = calibration_version

        # Calibrators: key is (horizon_min, threshold) -> IsotonicRegression
        self.calibrators: dict[tuple[int, float], IsotonicRegression] = {}
        self.calibration_status: dict[tuple[int, float], str] = {}
        self.calibration_metadata: dict[str, Any] = {}

    def compute_raw_probabilities(
        self,
        provider_predictions: Mapping[str, np.ndarray],
        provider_weights: Mapping[str, float],
    ) -> dict[float, np.ndarray]:
        """Compute smooth, mathematically bounded raw exceedance probabilities.

        P_raw(tau) = sum_p w_p * sigmoid(k * (forecast_p - tau))
        Guarantees:
        1. 0 < P < 1
        2. Monotonically non-increasing: P(tau_1) >= P(tau_2) for tau_1 <= tau_2
        """
        first_arr = next(iter(provider_predictions.values()))
        h, y, x = first_arr.shape

        tot_w = sum(max(0.0, float(w)) for w in provider_weights.values())
        norm_weights = {p: max(0.0, float(w)) / max(1e-6, tot_w) for p, w in provider_weights.items()}

        raw_probs: dict[float, np.ndarray] = {}
        for thr in self.thresholds:
            p_accum = np.zeros((h, y, x), dtype=np.float32)
            for pname, arr in provider_predictions.items():
                w = norm_weights.get(pname, 0.0)
                if w <= 0.0:
                    continue
                # Smooth logistic exceedance
                diff = np.nan_to_num(arr, nan=0.0) - thr
                sig = 1.0 / (1.0 + np.exp(-self.k * np.clip(diff, -15.0, 15.0)))
                p_accum += w * sig.astype(np.float32)

            raw_probs[thr] = np.clip(p_accum, 0.0, 1.0)

        # Enforce threshold monotonicity: P(0.1) >= P(1.0) >= P(5.0) >= P(10.0)
        for i in range(1, len(self.thresholds)):
            prev_thr = self.thresholds[i - 1]
            curr_thr = self.thresholds[i]
            raw_probs[curr_thr] = np.minimum(raw_probs[curr_thr], raw_probs[prev_thr])

        return raw_probs

    def fit_calibration_on_validation(
        self,
        val_samples: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """Fit isotonic regression models strictly on VALIDATION split observations.

        val_samples items:
        {
            "horizon_min": int,
            "raw_probs": {thr: np.ndarray},
            "obs_frame": np.ndarray,  # [Y, X]
            "valid_mask": np.ndarray, # [Y, X]
        }
        """
        fit_report: dict[str, Any] = {
            "calibration_split": "validation",
            "created_at": datetime.now(UTC).isoformat(),
            "thresholds": self.thresholds,
            "horizons": self.horizons_min,
            "calibrators": {},
        }

        for h_min in self.horizons_min:
            h_samples = [s for s in val_samples if s["horizon_min"] == h_min]

            for thr in self.thresholds:
                all_p_raw: list[np.ndarray] = []
                all_y_true: list[np.ndarray] = []

                for s in h_samples:
                    p_raw = s["raw_probs"][thr]
                    obs = s["obs_frame"]
                    vmask = s["valid_mask"] & np.isfinite(obs) & np.isfinite(p_raw)

                    if np.any(vmask):
                        all_p_raw.append(p_raw[vmask])
                        all_y_true.append((obs[vmask] > thr).astype(np.float32))

                if not all_p_raw:
                    self.calibration_status[(h_min, thr)] = "INSUFFICIENT_SUPPORT"
                    fit_report["calibrators"][f"{h_min}_{thr}"] = {
                        "status": "INSUFFICIENT_SUPPORT",
                        "reason": "no_valid_samples",
                    }
                    continue

                p_vec = np.concatenate(all_p_raw)
                y_vec = np.concatenate(all_y_true)

                n_total = len(p_vec)
                n_pos = int(np.sum(y_vec))
                n_neg = n_total - n_pos

                if n_pos < self.min_support_count or n_neg < self.min_support_count:
                    self.calibration_status[(h_min, thr)] = "INSUFFICIENT_SUPPORT"
                    fit_report["calibrators"][f"{h_min}_{thr}"] = {
                        "status": "INSUFFICIENT_SUPPORT",
                        "total_samples": n_total,
                        "positive_count": n_pos,
                        "negative_count": n_neg,
                        "min_required": self.min_support_count,
                    }
                else:
                    # Subsample if dataset is very large to ensure fast fitting
                    if n_total > 50000:
                        sub_idx = np.random.choice(n_total, size=50000, replace=False)
                        p_fit = p_vec[sub_idx]
                        y_fit = y_vec[sub_idx]
                    else:
                        p_fit = p_vec
                        y_fit = y_vec

                    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                    iso.fit(p_fit, y_fit)

                    self.calibrators[(h_min, thr)] = iso
                    self.calibration_status[(h_min, thr)] = "CALIBRATED_ISOTONIC"

                    fit_report["calibrators"][f"{h_min}_{thr}"] = {
                        "status": "CALIBRATED_ISOTONIC",
                        "total_samples": n_total,
                        "positive_count": n_pos,
                        "negative_count": n_neg,
                        "base_rate": float(n_pos / n_total),
                    }

        self.calibration_metadata = fit_report
        return fit_report

    def predict_probabilistic(
        self,
        *,
        fused_forecast: ForecastResult,
        provider_results: Mapping[str, ForecastResult],
        provider_weights: Mapping[str, float] | None = None,
    ) -> ProbabilisticForecastResult:
        """Produce calibrated exceedance probabilities from multi-model outputs."""
        h, y, x = fused_forecast.rainfall_mm_h.shape
        horizons = fused_forecast.horizons_min

        if provider_weights is None:
            # Fallback to equal provider weighting
            provider_weights = {p: 1.0 / len(provider_results) for p in provider_results}

        provider_preds = {pname: res.rainfall_mm_h for pname, res in provider_results.items()}
        raw_probs = self.compute_raw_probabilities(provider_preds, provider_weights)

        calibrated_probs: dict[float, np.ndarray] = {}
        status_dict: dict[str, str] = {}

        for thr in self.thresholds:
            p_thr = np.copy(raw_probs[thr])

            for lead_idx in range(h):
                h_min = horizons[lead_idx]
                key = (h_min, thr)
                status = self.calibration_status.get(key, "UNCALIBRATED")
                status_dict[f"{h_min}_{thr}"] = status

                if status == "CALIBRATED_ISOTONIC" and key in self.calibrators:
                    lead_slice = p_thr[lead_idx]
                    orig_shape = lead_slice.shape
                    flat_p = lead_slice.flatten()
                    cal_flat = self.calibrators[key].predict(flat_p)
                    p_thr[lead_idx] = cal_flat.reshape(orig_shape).astype(np.float32)

            calibrated_probs[thr] = np.clip(p_thr, 0.0, 1.0)

        # Monotonicity check across calibrated thresholds: P(>0.1) >= P(>1.0) >= P(>5.0) >= P(>10.0)
        for i in range(1, len(self.thresholds)):
            prev_thr = self.thresholds[i - 1]
            curr_thr = self.thresholds[i]
            calibrated_probs[curr_thr] = np.minimum(calibrated_probs[curr_thr], calibrated_probs[prev_thr])

        # Spread and disagreement from uncertainty envelope
        spread = fused_forecast.uncertainty.get("ensemble_spread_mean_mm_h", np.zeros((h, y, x), dtype=np.float32))
        if not isinstance(spread, np.ndarray) or spread.shape != (h, y, x):
            spread = np.zeros((h, y, x), dtype=np.float32)

        disagree = fused_forecast.uncertainty.get("provider_disagreement", np.zeros((h, y, x), dtype=np.float32))
        if not isinstance(disagree, np.ndarray) or disagree.shape != (h, y, x):
            disagree = np.zeros((h, y, x), dtype=np.float32)

        conf = fused_forecast.confidence
        if isinstance(conf, (int, float)):
            conf_arr = np.full(h, float(conf), dtype=np.float32)
        elif isinstance(conf, np.ndarray) and conf.ndim == 1 and len(conf) == h:
            conf_arr = conf.astype(np.float32)
        else:
            conf_arr = np.ones(h, dtype=np.float32)

        return ProbabilisticForecastResult(
            expected_rainfall_mm_h=fused_forecast.rainfall_mm_h,
            exceedance_probabilities=calibrated_probs,
            probability_thresholds_mm_h=self.thresholds,
            horizons_min=horizons,
            issue_time=fused_forecast.issue_time,
            valid_mask=fused_forecast.valid_mask,
            ensemble_spread=spread,
            provider_disagreement=disagree,
            forecast_confidence=conf_arr,
            calibration_status=status_dict,
            model_version=self.model_version,
            calibration_version=self.calibration_version,
            metadata={"raw_probabilities_available": True},
        )

    def save_calibration(self, filepath: str | Path) -> None:
        """Save fitted calibration curves and metadata to disk."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "calibrators": self.calibrators,
            "calibration_status": self.calibration_status,
            "calibration_metadata": self.calibration_metadata,
            "thresholds": self.thresholds,
            "horizons_min": self.horizons_min,
            "model_version": self.model_version,
            "calibration_version": self.calibration_version,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)

    def load_calibration(self, filepath: str | Path) -> None:
        """Load fitted calibration curves and metadata from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Calibration artifact not found at {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.calibrators = data["calibrators"]
        self.calibration_status = data["calibration_status"]
        self.calibration_metadata = data["calibration_metadata"]
        self.thresholds = data["thresholds"]
        self.horizons_min = data["horizons_min"]


def compute_probabilistic_metrics(
    y_true_binary: np.ndarray,
    p_pred: np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Calculate Brier score, BSS, ROC-AUC, PR-AUC, ECE, and reliability diagram bins."""
    y_t = np.asarray(y_true_binary, dtype=np.float32).flatten()
    p_p = np.clip(np.asarray(p_pred, dtype=np.float32).flatten(), 0.0, 1.0)

    n_total = len(y_t)
    n_pos = int(np.sum(y_t == 1.0))
    n_neg = n_total - n_pos

    if n_total == 0:
        return {"status": "insufficient_support", "sample_count": 0}

    # Brier Score
    bs = float(np.mean((p_p - y_t) ** 2))

    # Reference Brier Score (climatological base rate)
    base_rate = float(n_pos / n_total)
    bs_ref = float(base_rate * (1.0 - base_rate))

    # Brier Skill Score
    bss = float(1.0 - (bs / bs_ref)) if bs_ref > 1e-6 else 0.0

    # ROC-AUC and PR-AUC
    if n_pos > 0 and n_neg > 0:
        try:
            roc_auc = float(roc_auc_score(y_t, p_p))
        except Exception:
            roc_auc = "insufficient_support"
        try:
            pr_auc = float(average_precision_score(y_t, p_p))
        except Exception:
            pr_auc = "insufficient_support"
    else:
        roc_auc = "insufficient_support"
        pr_auc = "insufficient_support"

    # Reliability diagram bins
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins_data: list[dict[str, Any]] = []
    ece = 0.0

    for b in range(n_bins):
        low, high = bin_edges[b], bin_edges[b + 1]
        if b == n_bins - 1:
            in_bin = (p_p >= low) & (p_p <= high)
        else:
            in_bin = (p_p >= low) & (p_p < high)

        count = int(np.sum(in_bin))
        if count > 0:
            p_mean = float(np.mean(p_p[in_bin]))
            obs_freq = float(np.mean(y_t[in_bin]))
            cal_err = abs(p_mean - obs_freq)
            ece += (count / n_total) * cal_err
        else:
            p_mean = float(0.5 * (low + high))
            obs_freq = 0.0
            cal_err = 0.0

        bins_data.append({
            "bin_index": b,
            "bin_range": [round(float(low), 2), round(float(high), 2)],
            "count": count,
            "fraction": float(count / n_total),
            "predicted_prob_mean": round(p_mean, 4),
            "observed_frequency": round(obs_freq, 4),
            "calibration_error": round(cal_err, 4),
        })

    return {
        "status": "evaluated",
        "sample_count": n_total,
        "positive_count": n_pos,
        "negative_count": n_neg,
        "base_rate": round(base_rate, 4),
        "brier_score": round(bs, 6),
        "brier_reference": round(bs_ref, 6),
        "brier_skill_score": round(bss, 6),
        "expected_calibration_error": round(ece, 6),
        "roc_auc": round(roc_auc, 4) if isinstance(roc_auc, float) else roc_auc,
        "pr_auc": round(pr_auc, 4) if isinstance(pr_auc, float) else pr_auc,
        "reliability_bins": bins_data,
    }
