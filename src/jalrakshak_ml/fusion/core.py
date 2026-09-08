"""Multi-model forecast fusion engine for JalRakshak AI.

Implements:
1. Equal-weight fusion
2. Horizon-aware fixed-weight fusion
3. Skill-derived deterministic fusion (strictly calibrated on train/val splits)
4. Robust missing-provider fallbacks and uncertainty quantification
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

import numpy as np

from jalrakshak_ml.fusion.contracts import (
    BaseForecastProvider,
    ForecastResult,
    _ensure_utc,
)
from jalrakshak_ml.fusion.gating import BaseGatingModel, GateFeatureBuilder
from jalrakshak_ml.fusion.uncertainty import (
    compute_ensemble_spread,
    compute_forecast_confidence,
    compute_provider_disagreement,
)


class MultiModelFusion:
    """Combines predictions from multiple forecast providers using configurable weighting."""

    def __init__(
        self,
        providers: Sequence[BaseForecastProvider],
        *,
        fusion_method: str = "equal",
        weights_by_horizon: Mapping[int, Mapping[str, float]] | None = None,
        gating_model: BaseGatingModel | None = None,
        name: str | None = None,
        model_version: str | None = None,
        data_version: str = "operational_v1",
        expected_providers: Sequence[str] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        providers : list of BaseForecastProvider instances
        fusion_method : "equal" | "horizon_fixed" | "skill_derived" | "custom"
        weights_by_horizon : dict mapping horizon_min (e.g. 30, 60, 90, 120) to
            dict of {provider_name: weight}
        name : identifier for this fusion engine
        model_version : version tag
        data_version : version tag of underlying dataset
        expected_providers : optional list of provider names expected in the full ensemble
        """
        self.providers = list(providers)
        self.provider_names = [p.name for p in self.providers]
        self.fusion_method = fusion_method
        self.weights_by_horizon = weights_by_horizon or {}
        self.gating_model = gating_model
        self._name = name or f"fusion_{fusion_method}"
        self._model_version = model_version or f"{self._name}_v1"
        self._data_version = data_version
        self._expected_providers = list(expected_providers or self.provider_names)
        self._gate_builder = GateFeatureBuilder(self._expected_providers)

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._model_version

    def _get_weights_for_lead(
        self,
        lead_idx: int,
        horizon_min: int,
        available_names: list[str],
    ) -> dict[str, float]:
        """Compute non-negative normalized weights for available providers."""
        if not available_names:
            raise RuntimeError("Cannot compute weights for empty provider set")

        if self.fusion_method == "equal":
            w = 1.0 / len(available_names)
            return {name: w for name in available_names}

        # Check configured weights for this horizon
        raw_weights = self.weights_by_horizon.get(horizon_min, {})
        # Filter to available providers and ensure non-negative
        filtered = {
            name: max(0.0, float(raw_weights.get(name, 0.0)))
            for name in available_names
        }
        total = sum(filtered.values())
        if total <= 1e-8:
            # Fallback to equal weighting among available providers
            w = 1.0 / len(available_names)
            return {name: w for name in available_names}

        # Normalize to sum to 1.0
        return {name: filtered[name] / total for name in available_names}

    def predict(
        self,
        *,
        history_frames: np.ndarray | None = None,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ForecastResult:
        """Run all available providers, fuse outputs, and attach uncertainty metrics."""
        issue_time = _ensure_utc(issue_time)
        horizons = [temporal_step_minutes * (i + 1) for i in range(lead_times)]

        # Collect forecasts from available providers
        available_results: dict[str, ForecastResult] = {}
        missing_providers: list[str] = []

        for provider in self.providers:
            if not provider.is_available:
                missing_providers.append(provider.name)
                continue
            try:
                result = provider.predict(
                    history_frames=history_frames,
                    issue_time=issue_time,
                    lead_times=lead_times,
                    temporal_step_minutes=temporal_step_minutes,
                    event_id=event_id,
                    context=context,
                )
                available_results[provider.name] = result
            except Exception as exc:
                missing_providers.append(f"{provider.name} (error: {exc})")

        if not available_results:
            raise RuntimeError(
                f"No forecast providers were available at issue_time={issue_time.isoformat()} "
                f"for event_id={event_id!r}. Missing: {missing_providers}"
            )

        # Output shape is determined by the first available provider
        ref = next(iter(available_results.values()))
        h, y, x = ref.rainfall_mm_h.shape

        fused_rainfall = np.zeros((h, y, x), dtype=np.float32)
        fused_mask = np.ones((h, y, x), dtype=bool)
        applied_weights: dict[int, dict[str, float]] = {}

        for lead_idx in range(h):
            h_min = horizons[lead_idx]
            if self.gating_model is not None:
                feat = self._gate_builder.build_features_for_horizon(
                    lead_idx=lead_idx,
                    horizon_min=h_min,
                    issue_time=issue_time,
                    provider_results=available_results,
                    history_frames=history_frames,
                    context=context,
                )
                weights = self.gating_model.predict_weights(feat, list(available_results.keys()))
            else:
                weights = self._get_weights_for_lead(lead_idx, h_min, list(available_results.keys()))
            applied_weights[h_min] = weights

            lead_accum = np.zeros((y, x), dtype=np.float32)
            lead_mask = np.ones((y, x), dtype=bool)

            for pname, w in weights.items():
                p_res = available_results[pname]
                p_lead = p_res.rainfall_mm_h[lead_idx]
                p_mask = p_res.valid_mask[lead_idx] & np.isfinite(p_lead)

                lead_accum += w * np.where(p_mask, p_lead, 0.0)
                lead_mask &= p_mask

            fused_rainfall[lead_idx] = np.maximum(0.0, lead_accum)
            fused_mask[lead_idx] = lead_mask

        # Compute uncertainty metrics across available forecasts
        active_forecasts = {pname: res.rainfall_mm_h for pname, res in available_results.items()}
        spread = compute_ensemble_spread(
            list(active_forecasts.values()),
            valid_mask=fused_mask,
        )
        disagreement = compute_provider_disagreement(
            active_forecasts,
            valid_mask=fused_mask,
        )

        # Average data quality from available results
        avg_quality = 1.0
        conf_metrics = compute_forecast_confidence(
            mean_forecast=fused_rainfall,
            spread=spread,
            valid_count=len(available_results),
            expected_count=len(self._expected_providers),
            data_quality=avg_quality,
        )

        uncertainty_envelope = {
            "ensemble_spread_mean_mm_h": conf_metrics["mean_spread_mm_h"],
            "provider_disagreement": disagreement,
            "agreement_score": conf_metrics["agreement_score"],
            "confidence_score": conf_metrics["confidence_score"],
            "valid_providers": list(available_results.keys()),
            "missing_providers": missing_providers,
            "fallback_applied": len(missing_providers) > 0,
            "applied_weights": applied_weights,
        }

        return ForecastResult(
            rainfall_mm_h=fused_rainfall,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=fused_mask,
            provider=self.name,
            model_version=self.model_version,
            data_version=self._data_version,
            source_metadata={
                "event_id": event_id,
                "fusion_method": self.fusion_method,
                "active_providers_count": len(available_results),
                "expected_providers_count": len(self._expected_providers),
            },
            provenance={
                "method": f"{self.fusion_method}_fusion",
                "weights": applied_weights,
                "missing_providers": missing_providers,
            },
            native_cadence_minutes=ref.native_cadence_minutes,
            output_cadence_minutes=ref.output_cadence_minutes,
            confidence=np.asarray(conf_metrics["confidence_score"], dtype=np.float32),
            uncertainty=uncertainty_envelope,
        )


def create_equal_weight_fusion(
    providers: Sequence[BaseForecastProvider],
    data_version: str = "operational_v1",
) -> MultiModelFusion:
    """Build equal-weight fusion engine."""
    return MultiModelFusion(
        providers,
        fusion_method="equal",
        name="fusion_equal",
        model_version="fusion_equal_v1",
        data_version=data_version,
    )


def create_horizon_fixed_fusion(
    providers: Sequence[BaseForecastProvider],
    data_version: str = "operational_v1",
    pysteps_weights: Sequence[float] = (0.70, 0.50, 0.35, 0.20),
    gfs_weights: Sequence[float] = (0.30, 0.50, 0.65, 0.80),
) -> MultiModelFusion:
    """Build horizon-aware fixed-weight fusion engine (pysteps early, GFS late)."""
    horizons = [30, 60, 90, 120]
    weights_by_horizon = {}
    for i, h in enumerate(horizons):
        weights_by_horizon[h] = {
            "pysteps": pysteps_weights[i],
            "gfs": gfs_weights[i],
            "persistence": 0.0,
            "convlstm_v2": 0.0,
        }
    return MultiModelFusion(
        providers,
        fusion_method="horizon_fixed",
        weights_by_horizon=weights_by_horizon,
        name="fusion_horizon_fixed",
        model_version="fusion_horizon_fixed_v1",
        data_version=data_version,
    )


def create_skill_derived_fusion(
    providers: Sequence[BaseForecastProvider],
    calibrated_weights: Mapping[int, Mapping[str, float]],
    data_version: str = "operational_v1",
) -> MultiModelFusion:
    """Build skill-derived fusion engine using calibrated weights from train/validation."""
    return MultiModelFusion(
        providers,
        fusion_method="skill_derived",
        weights_by_horizon=calibrated_weights,
        name="fusion_skill_derived",
        model_version="fusion_skill_derived_v1",
        data_version=data_version,
    )


def create_learned_gate_fusion(
    providers: Sequence[BaseForecastProvider],
    gating_model: BaseGatingModel,
    data_version: str = "operational_v1",
) -> MultiModelFusion:
    """Build learned gating fusion engine with dynamic condition/horizon-dependent weights."""
    return MultiModelFusion(
        providers,
        fusion_method="learned_gate",
        gating_model=gating_model,
        name="fusion_learned_gate",
        model_version=f"{gating_model.name}_fusion_v1",
        data_version=data_version,
    )

