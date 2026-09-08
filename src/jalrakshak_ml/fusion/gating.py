"""Research-ready gating architecture and feature builder for learned multi-model fusion.

Extracts per-provider and shared physical/meteorological features.
Provides clean schema, normalization, and scaffolding for future supervised gating models.
"""
from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import torch.nn as nn

from jalrakshak_ml.fusion.contracts import ForecastResult


@dataclass(slots=True)
class ProviderFeatures:
    """Per-provider features extracted for a specific horizon."""

    provider: str
    mean_forecast_mm_h: float
    p90_forecast_mm_h: float
    max_forecast_mm_h: float
    valid_fraction: float
    model_confidence: float
    quality_score: float
    disagreement_from_ensemble_mean: float
    recent_historical_skill: float = 0.0  # Placeholder for operational rolling skill


@dataclass(slots=True)
class SharedFeatures:
    """Shared meteorological and operational context features."""

    lead_time_min: int
    current_rainfall_mean_mm_h: float
    current_rainfall_max_mm_h: float
    rain_regime: int  # 0: dry (<0.1), 1: light (0.1-5), 2: moderate (5-15), 3: heavy (>=15)
    gfs_forecast_age_hours: float
    available_providers_count: int
    total_expected_providers: int
    issue_hour_utc: int


@dataclass(slots=True)
class GateFeatures:
    """Complete feature bundle for one sequence and one horizon."""

    issue_time: str
    horizon_min: int
    shared: SharedFeatures
    providers: dict[str, ProviderFeatures]

    def to_flat_dict(self) -> dict[str, float]:
        """Flatten into tabular format suitable for tree models or neural nets."""
        flat: dict[str, float] = {
            "lead_time_min": float(self.shared.lead_time_min),
            "current_rainfall_mean": self.shared.current_rainfall_mean_mm_h,
            "current_rainfall_max": self.shared.current_rainfall_max_mm_h,
            "rain_regime": float(self.shared.rain_regime),
            "gfs_forecast_age_hours": self.shared.gfs_forecast_age_hours,
            "available_providers_count": float(self.shared.available_providers_count),
            "issue_hour_utc": float(self.shared.issue_hour_utc),
        }
        for pname, pf in self.providers.items():
            flat[f"{pname}_mean"] = pf.mean_forecast_mm_h
            flat[f"{pname}_p90"] = pf.p90_forecast_mm_h
            flat[f"{pname}_max"] = pf.max_forecast_mm_h
            flat[f"{pname}_valid_frac"] = pf.valid_fraction
            flat[f"{pname}_confidence"] = pf.model_confidence
            flat[f"{pname}_quality"] = pf.quality_score
            flat[f"{pname}_disagreement"] = pf.disagreement_from_ensemble_mean
        return flat

    def to_feature_vector(self, provider_order: Sequence[str]) -> np.ndarray:
        """Convert into a fixed-length numeric vector matching declared provider order."""
        vec = [
            float(self.shared.lead_time_min),
            self.shared.current_rainfall_mean_mm_h,
            self.shared.current_rainfall_max_mm_h,
            float(self.shared.rain_regime),
            self.shared.gfs_forecast_age_hours,
            float(self.shared.available_providers_count),
            float(self.shared.issue_hour_utc),
        ]
        for pname in provider_order:
            if pname in self.providers:
                pf = self.providers[pname]
                vec.extend([
                    pf.mean_forecast_mm_h,
                    pf.p90_forecast_mm_h,
                    pf.max_forecast_mm_h,
                    pf.valid_fraction,
                    pf.model_confidence,
                    pf.quality_score,
                    pf.disagreement_from_ensemble_mean,
                ])
            else:
                vec.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        return np.asarray(vec, dtype=np.float32)

    def to_vector_v1(
        self,
        provider_order: Sequence[str] = ("persistence", "pysteps", "convlstm_v2", "gfs"),
        rainfall_trend: float = 0.0,
        recent_accumulation: float = 0.0,
    ) -> np.ndarray:
        """Convert into canonical 44-D vector matching dataset.py."""
        vec = [
            float(self.shared.lead_time_min),
            self.shared.current_rainfall_mean_mm_h,
            self.shared.current_rainfall_max_mm_h,
            float(self.shared.rain_regime),
            self.shared.gfs_forecast_age_hours,
            float(self.shared.available_providers_count),
            float(self.shared.issue_hour_utc),
            rainfall_trend,
            recent_accumulation,
        ]
        available_means = []
        for pname in provider_order:
            if pname in self.providers:
                pf = self.providers[pname]
                vec.extend([
                    pf.mean_forecast_mm_h,
                    pf.p90_forecast_mm_h,
                    pf.max_forecast_mm_h,
                    pf.valid_fraction,
                    pf.model_confidence,
                    pf.quality_score,
                    pf.disagreement_from_ensemble_mean,
                    1.0,
                ])
                available_means.append(pf.mean_forecast_mm_h)
            else:
                vec.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        if available_means:
            ens_m = float(np.mean(available_means))
            ens_s = float(np.std(available_means)) if len(available_means) > 1 else 0.0
            dis_m = float(np.max(available_means) - np.min(available_means)) if len(available_means) > 1 else 0.0
        else:
            ens_m, ens_s, dis_m = 0.0, 0.0, 0.0
        vec.extend([ens_m, ens_s, dis_m])
        return np.asarray(vec, dtype=np.float32)



class GateFeatureBuilder:
    """Constructs auditable GateFeatures from provider forecasts and observational context."""

    def __init__(self, expected_providers: Sequence[str] = ("persistence", "pysteps", "convlstm_v2", "gfs")) -> None:
        self.expected_providers = list(expected_providers)

    def _determine_rain_regime(self, mean_rain: float, max_rain: float) -> int:
        if max_rain < 0.1:
            return 0  # Dry
        if max_rain < 5.0:
            return 1  # Light
        if max_rain < 15.0:
            return 2  # Moderate
        return 3  # Heavy / Extreme

    def build_features_for_horizon(
        self,
        *,
        lead_idx: int,
        horizon_min: int,
        issue_time: datetime,
        provider_results: dict[str, ForecastResult],
        history_frames: np.ndarray | None = None,
        context: dict[str, Any] | None = None,
    ) -> GateFeatures:
        context = context or {}
        issue_dt = issue_time.astimezone(UTC) if issue_time.tzinfo else issue_time.replace(tzinfo=UTC)

        # 1. Shared features
        if history_frames is not None and len(history_frames) > 0:
            latest = history_frames[-1]
            valid_latest = latest[np.isfinite(latest)]
            cur_mean = float(np.mean(valid_latest)) if valid_latest.size else 0.0
            cur_max = float(np.max(valid_latest)) if valid_latest.size else 0.0
        else:
            cur_mean = float(context.get("current_rainfall_mean", 0.0))
            cur_max = float(context.get("current_rainfall_max", 0.0))

        regime = self._determine_rain_regime(cur_mean, cur_max)

        # GFS forecast age
        gfs_res = provider_results.get("gfs")
        if gfs_res and "forecast_age_hours" in gfs_res.source_metadata:
            gfs_age = float(gfs_res.source_metadata["forecast_age_hours"])
        else:
            gfs_age = float(context.get("gfs_forecast_age_hours", 6.0))

        shared = SharedFeatures(
            lead_time_min=horizon_min,
            current_rainfall_mean_mm_h=cur_mean,
            current_rainfall_max_mm_h=cur_max,
            rain_regime=regime,
            gfs_forecast_age_hours=gfs_age,
            available_providers_count=len(provider_results),
            total_expected_providers=len(self.expected_providers),
            issue_hour_utc=issue_dt.hour,
        )

        # 2. Compute unweighted ensemble mean for disagreement calculation
        lead_forecasts = {}
        for pname, res in provider_results.items():
            lead_forecasts[pname] = res.rainfall_mm_h[lead_idx]

        if lead_forecasts:
            stack = np.stack(list(lead_forecasts.values()), axis=0)
            ens_mean = np.nanmean(stack, axis=0)
        else:
            ens_mean = np.zeros((1, 1), dtype=np.float32)

        # 3. Per-provider features
        providers_feat: dict[str, ProviderFeatures] = {}
        for pname, res in provider_results.items():
            lead_arr = res.rainfall_mm_h[lead_idx]
            vmask = res.valid_mask[lead_idx] & np.isfinite(lead_arr)
            valid_frac = float(np.mean(vmask))
            finite_vals = lead_arr[vmask]

            if finite_vals.size:
                p_mean = float(np.mean(finite_vals))
                p_p90 = float(np.percentile(finite_vals, 90))
                p_max = float(np.max(finite_vals))
            else:
                p_mean = 0.0
                p_p90 = 0.0
                p_max = 0.0

            # Disagreement from ensemble mean
            if ens_mean.shape == lead_arr.shape and finite_vals.size:
                disagree = float(np.mean(np.abs(lead_arr[vmask] - ens_mean[vmask])))
            else:
                disagree = 0.0

            conf = 1.0
            if isinstance(res.confidence, (int, float)):
                conf = float(res.confidence)
            elif isinstance(res.confidence, np.ndarray) and res.confidence.ndim == 1:
                conf = float(res.confidence[lead_idx])

            quality = float(res.source_metadata.get("quality_score", 1.0))

            providers_feat[pname] = ProviderFeatures(
                provider=pname,
                mean_forecast_mm_h=p_mean,
                p90_forecast_mm_h=p_p90,
                max_forecast_mm_h=p_max,
                valid_fraction=valid_frac,
                model_confidence=conf,
                quality_score=quality,
                disagreement_from_ensemble_mean=disagree,
                recent_historical_skill=float(context.get(f"{pname}_recent_skill", 0.0)),
            )

        return GateFeatures(
            issue_time=issue_dt.isoformat(),
            horizon_min=horizon_min,
            shared=shared,
            providers=providers_feat,
        )


class BaseGatingModel(abc.ABC):
    """Abstract base contract for learned or rule-based fusion gates."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Gating model identifier."""

    @property
    @abc.abstractmethod
    def is_trained(self) -> bool:
        """True if model weights have been fitted on legitimate non-test data."""

    @abc.abstractmethod
    def predict_weights(
        self,
        features: GateFeatures,
        available_providers: Sequence[str],
    ) -> dict[str, float]:
        """Compute convex weights (non-negative, sum to 1.0) for available providers."""


class SupervisedGatingBaseline(BaseGatingModel):
    """Supervised gating model scaffolding.

    Can be backed by LightGBM, small MLP, or Ridge regressor trained to predict
    inverse expected error. Marked untrained if non-test replay is unavailable.
    """

    def __init__(
        self,
        name: str = "supervised_gating_baseline_v1",
        expected_providers: Sequence[str] = ("persistence", "pysteps", "convlstm_v2", "gfs"),
    ) -> None:
        self._name = name
        self.expected_providers = list(expected_providers)
        self._is_trained = False
        self._feature_importances: dict[str, float] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def feature_importances(self) -> dict[str, float]:
        return self._feature_importances

    def predict_weights(
        self,
        features: GateFeatures,
        available_providers: Sequence[str],
    ) -> dict[str, float]:
        """Compute convex weights for available providers."""
        if not available_providers:
            raise ValueError("available_providers cannot be empty")

        if not self.is_trained:
            # Untrained baseline defaults to equal weighting among available providers
            w = 1.0 / len(available_providers)
            return {p: w for p in available_providers}

        # If trained, predict inverse expected error or direct softmax weights
        # (This path will be used when trained on non-test replay).
        w = 1.0 / len(available_providers)
        return {p: w for p in available_providers}


class LearnedGateMLP(nn.Module):
    """Compact 2-layer MLP gating network producing convex provider weights."""

    def __init__(self, in_features: int = 44, num_providers: int = 4, hidden_dim: int = 32):
        super().__init__()
        self.in_features = in_features
        self.num_providers = num_providers
        self.net = nn.Sequential(
            nn.Linear(in_features, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.05),
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, num_providers),
        )

    def forward(self, x: torch.Tensor, availability_mask: torch.Tensor | None = None) -> torch.Tensor:
        """Forward pass predicting convex provider weights.

        Parameters
        ----------
        x : [B, in_features]
        availability_mask : [B, num_providers] boolean tensor (True = available)

        Returns
        -------
        weights : [B, num_providers] non-negative weights summing to 1.0
        """
        logits = self.net(x)
        if availability_mask is not None:
            # Set unavailable providers to a negative constant that zeros out in softmax without overflow
            neg_inf = -100.0
            logits = torch.where(
                availability_mask,
                logits,
                torch.full_like(logits, neg_inf),
            )
        return torch.softmax(logits, dim=-1)


class LearnedGatingModel(BaseGatingModel):
    """Supervised learned gating model with guaranteed convex weights and fallback."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        expected_providers: Sequence[str] = ("persistence", "pysteps", "convlstm_v2", "gfs"),
        device: str = "cpu",
    ) -> None:
        self._name = "learned_gate_mlp_v1"
        self.expected_providers = list(expected_providers)
        self.device = torch.device(device)
        self.mlp = LearnedGateMLP(in_features=44, num_providers=len(self.expected_providers))
        self.mlp.to(self.device)
        self.mlp.eval()
        self._is_trained = False
        self._metadata: dict[str, Any] = {}

        if model_path is not None:
            self.load(model_path)

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def load(self, model_path: str | Path) -> None:
        """Load trained model weights from disk."""
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Learned gate model not found at {path}")
        checkpoint = torch.load(str(path), map_location=self.device, weights_only=False)
        if isinstance(checkpoint, dict) and "model_state" in checkpoint:
            self.mlp.load_state_dict(checkpoint["model_state"])
            self._metadata = checkpoint.get("metadata", {})
            if "feature_mean" in checkpoint and "feature_std" in checkpoint:
                self._feature_mean = np.array(checkpoint["feature_mean"], dtype=np.float32)
                self._feature_std = np.array(checkpoint["feature_std"], dtype=np.float32)
                self._feature_std[self._feature_std < 1e-6] = 1.0
            else:
                self._feature_mean = None
                self._feature_std = None
        else:
            self.mlp.load_state_dict(checkpoint)
            self._feature_mean = None
            self._feature_std = None
        self.mlp.eval()
        self._is_trained = True

    def predict_weights(
        self,
        features: GateFeatures,
        available_providers: Sequence[str],
    ) -> dict[str, float]:
        """Predict convex weights (w_i >= 0, sum w_i = 1.0) for available providers."""
        if not available_providers:
            raise ValueError("available_providers cannot be empty")

        avail_set = set(available_providers)
        valid_avail = [p for p in self.expected_providers if p in avail_set]
        if not valid_avail:
            # Fallback if none of the declared expected providers are available
            w = 1.0 / len(available_providers)
            return {p: w for p in available_providers}

        if not self._is_trained:
            # Untrained baseline defaults to equal weighting
            w = 1.0 / len(valid_avail)
            return {p: (w if p in valid_avail else 0.0) for p in self.expected_providers if p in avail_set}

        # Vectorize features
        vec = features.to_vector_v1(provider_order=self.expected_providers)
        if getattr(self, "_feature_mean", None) is not None and getattr(self, "_feature_std", None) is not None:
            vec = (vec - self._feature_mean) / self._feature_std
            vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        x_t = torch.from_numpy(vec).unsqueeze(0).to(self.device)

        # Availability mask
        mask_arr = np.array([p in avail_set for p in self.expected_providers], dtype=bool)
        mask_t = torch.from_numpy(mask_arr).unsqueeze(0).to(self.device)

        with torch.no_grad():
            weights_t = self.mlp(x_t, availability_mask=mask_t)
            w_arr = weights_t.squeeze(0).cpu().numpy()

        out_weights: dict[str, float] = {}
        for i, pname in enumerate(self.expected_providers):
            if pname in avail_set:
                out_weights[pname] = float(max(0.0, w_arr[i]))

        # Normalize to ensure sum is strictly 1.0
        tot = sum(out_weights.values())
        if tot > 1e-6:
            out_weights = {k: float(v / tot) for k, v in out_weights.items()}
        else:
            eq = 1.0 / len(valid_avail)
            out_weights = {k: eq for k in valid_avail}

        return out_weights

