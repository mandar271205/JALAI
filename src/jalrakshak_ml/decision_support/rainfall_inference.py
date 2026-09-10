"""Rainfall Unified Inference Layer: Model-First with AI and Deterministic Fallback.

Strictly adheres to:
1. Model-First: Numerical forecast (PySTEPS / ConvLSTM V3 / frozen winner) remains authoritative.
2. Provisional AI: When model is unavailable, meteorological evidence powers structured provisional assessments.
3. Insufficient Evidence: Graceful degrade when evidence is absent.
4. Truthful provenance: Never attributes LLM output to ConvLSTM/PySTEPS.
"""
from __future__ import annotations

import logging
from typing import Any

from jalrakshak_ml.decision_support.arbitration import arbitrate_rainfall
from jalrakshak_ml.decision_support.provenance import create_provenance
from jalrakshak_ml.decision_support.provider_router import ProviderRouter
from jalrakshak_ml.decision_support.schemas import (
    InferenceMode,
    IntensityBand,
    RainfallInferenceInput,
    RainfallInferenceOutput,
    SeverityLevel,
    TrendDirection,
)

logger = logging.getLogger("jalrakshak.decision_support.rainfall")


def derive_deterministic_rainfall_baseline(input_data: RainfallInferenceInput) -> tuple[SeverityLevel, TrendDirection, float, IntensityBand, str, list[str], str]:
    """Deterministic rule-based baseline when AI is unavailable or fails."""
    rain_rates: list[float] = []
    if input_data.rainfall_mm_h:
        rain_rates.extend([float(r) for r in input_data.rainfall_mm_h if r is not None])
    if input_data.latest_observation_mm_h is not None:
        rain_rates.append(float(input_data.latest_observation_mm_h))
    if input_data.persistence_baseline_mm_h is not None:
        rain_rates.append(float(input_data.persistence_baseline_mm_h))
    if input_data.gfs_context and "precipitation_mm_h" in input_data.gfs_context:
        try:
            rain_rates.append(float(input_data.gfs_context["precipitation_mm_h"]))
        except (ValueError, TypeError):
            pass

    max_rate = max(rain_rates) if rain_rates else 0.0

    if max_rate >= 65.0:
        sev = SeverityLevel.SEVERE
        band = IntensityBand(min=50.0, max=round(max_rate * 1.2, 1))
        action = "Issue immediate flash waterlogging warnings and activate high-capacity pumping stations."
    elif max_rate >= 35.0:
        sev = SeverityLevel.HIGH
        band = IntensityBand(min=30.0, max=round(max_rate * 1.1, 1))
        action = "Alert ward response teams and monitor stormwater drains along arterial transit routes."
    elif max_rate >= 10.0:
        sev = SeverityLevel.MODERATE
        band = IntensityBand(min=10.0, max=30.0)
        action = "Standard monsoon vigilance; monitor localized runoff in low-lying sectors."
    else:
        sev = SeverityLevel.LOW
        band = IntensityBand(min=0.0, max=10.0)
        action = "Normal monitoring; no emergency deployment required."

    trend = TrendDirection.UNKNOWN
    if input_data.recent_observation_trend:
        trend_str = input_data.recent_observation_trend.upper()
        if "INCREAS" in trend_str:
            trend = TrendDirection.INCREASING
        elif "DECREAS" in trend_str:
            trend = TrendDirection.DECREASING
        elif "STABLE" in trend_str:
            trend = TrendDirection.STABLE

    summary = f"Deterministic baseline assessment indicates {sev.value} rainfall potential based on available meteorological signals."
    factors = [f"Max observed/replayed rain rate: {max_rate:.1f} mm/h"]
    if input_data.gfs_context:
        factors.append("Synoptic GFS forecast context incorporated")

    return sev, trend, 0.70, band, summary, factors, action


async def infer_rainfall(
    input_data: RainfallInferenceInput,
    router: ProviderRouter | None = None,
) -> RainfallInferenceOutput:
    """Execute unified model-first rainfall inference with AI fallback and strict safety."""
    active_router = router or ProviderRouter()

    # Determine if numerical model output is genuinely present
    has_numerical_model = bool(
        input_data.rainfall_mm_h and len(input_data.rainfall_mm_h) > 0 and input_data.model_name
    )

    # Check for complete lack of evidence (Insufficient Evidence)
    has_evidence = (
        has_numerical_model
        or (input_data.latest_observation_mm_h is not None)
        or (input_data.persistence_baseline_mm_h is not None)
        or (input_data.gfs_context is not None and len(input_data.gfs_context) > 0)
    )

    if not has_evidence:
        logger.warning("No numerical model and no meteorological evidence supplied for rainfall.")
        prov = create_provenance(
            source_mode=InferenceMode.INSUFFICIENT_EVIDENCE,
            primary_model_available=False,
            ai_assistance_used=False,
            fallback_used=True,
            fallback_reason="No numerical model or meteorological observations supplied",
            evidence_ids=input_data.evidence_ids,
            data_version=input_data.data_version,
        )
        return RainfallInferenceOutput(
            severity=SeverityLevel.LOW,
            trend=TrendDirection.UNKNOWN,
            confidence=0.10,
            expected_intensity_band_mm_h=IntensityBand(min=None, max=None),
            summary="Insufficient meteorological evidence available to construct a reliable rainfall assessment.",
            key_factors=["Missing radar/satellite observation", "Missing synoptic NWP context"],
            recommended_action="Await fresh telemetry feed from IMD radar or GPM satellite passes.",
            evidence_ids=input_data.evidence_ids,
            numerical_forecast=None,
            provenance=prov,
        )

    # Route request through Three-Model Router
    candidate, gen_slot, gen_provider, gen_model, failover_used, failover_reason, verifier_res = (
        await active_router.route_rainfall_inference(input_data, has_numerical_model=has_numerical_model)
    )

    numerical_payload: dict[str, Any] | None = None
    if has_numerical_model:
        numerical_payload = {
            "forecast_horizons_minutes": input_data.forecast_horizons_minutes,
            "rainfall_mm_h": input_data.rainfall_mm_h,
            "probability_gt_1": input_data.probability_gt_1,
            "probability_gt_5": input_data.probability_gt_5,
            "probability_gt_10": input_data.probability_gt_10,
            "quality_score": input_data.quality_score,
            "model_confidence": input_data.model_confidence,
            "model_name": input_data.model_name,
            "model_version": input_data.model_version,
        }

    # Case A: AI generation succeeded (Model 1 or Model 2)
    if candidate is not None:
        (
            severity,
            confidence,
            intensity_band,
            summary,
            key_factors,
            _conflicts,
            arbitration_fallback,
        ) = arbitrate_rainfall(
            input_data,
            candidate,
            has_numerical_model=has_numerical_model,
            verifier_result=verifier_res,
        )

        # If verifier rejected candidate completely, fall back to deterministic baseline
        if arbitration_fallback:
            logger.warning(f"Arbitration triggered fallback: {arbitration_fallback}")
            sev_b, trend_b, conf_b, band_b, sum_b, fact_b, act_b = derive_deterministic_rainfall_baseline(input_data)
            prov = create_provenance(
                source_mode=InferenceMode.NUMERICAL_MODEL if has_numerical_model else InferenceMode.DETERMINISTIC_FALLBACK,
                primary_model_available=has_numerical_model,
                numerical_model_name=input_data.model_name if has_numerical_model else None,
                numerical_model_version=input_data.model_version if has_numerical_model else None,
                ai_assistance_used=False,
                ai_failover_used=failover_used,
                ai_failover_reason=arbitration_fallback,
                ai_verifier_used=verifier_res is not None,
                ai_verifier_verdict=verifier_res.verdict.value if verifier_res else None,
                fallback_used=True,
                fallback_reason=arbitration_fallback,
                evidence_ids=input_data.evidence_ids,
                data_version=input_data.data_version,
            )
            return RainfallInferenceOutput(
                severity=sev_b,
                trend=trend_b,
                confidence=conf_b,
                expected_intensity_band_mm_h=band_b,
                summary=sum_b,
                key_factors=fact_b,
                recommended_action=act_b,
                evidence_ids=input_data.evidence_ids,
                numerical_forecast=numerical_payload,
                provenance=prov,
            )

        source_mode = (
            InferenceMode.MODEL_PLUS_AI if has_numerical_model else InferenceMode.PROVISIONAL_AI
        )

        prov = create_provenance(
            source_mode=source_mode,
            primary_model_available=has_numerical_model,
            numerical_model_name=input_data.model_name if has_numerical_model else None,
            numerical_model_version=input_data.model_version if has_numerical_model else None,
            ai_assistance_used=True,
            ai_generation_used=True,
            ai_generator_slot=gen_slot,
            ai_generator_provider=gen_provider,
            ai_generator_model=gen_model,
            ai_failover_used=failover_used,
            ai_failover_reason=failover_reason,
            ai_verifier_used=verifier_res is not None,
            ai_verifier_provider=active_router.llm3.name if verifier_res else None,
            ai_verifier_model=active_router.llm3.model_id if verifier_res else None,
            ai_verifier_verdict=verifier_res.verdict.value if verifier_res else None,
            fallback_used=False,
            evidence_ids=input_data.evidence_ids,
            data_version=input_data.data_version,
        )

        return RainfallInferenceOutput(
            severity=severity,
            trend=candidate.trend,
            confidence=confidence,
            expected_intensity_band_mm_h=intensity_band,
            summary=summary,
            key_factors=key_factors,
            recommended_action=candidate.recommended_action,
            evidence_ids=input_data.evidence_ids,
            numerical_forecast=numerical_payload,
            provenance=prov,
        )

    # Case B: AI was unavailable, disabled, or all providers failed -> Deterministic Fallback
    sev_b, trend_b, conf_b, band_b, sum_b, fact_b, act_b = derive_deterministic_rainfall_baseline(input_data)
    source_mode = (
        InferenceMode.NUMERICAL_MODEL if has_numerical_model else InferenceMode.DETERMINISTIC_FALLBACK
    )

    prov = create_provenance(
        source_mode=source_mode,
        primary_model_available=has_numerical_model,
        numerical_model_name=input_data.model_name if has_numerical_model else None,
        numerical_model_version=input_data.model_version if has_numerical_model else None,
        ai_assistance_used=False,
        ai_failover_used=failover_used,
        ai_failover_reason=failover_reason,
        fallback_used=True,
        fallback_reason=failover_reason or "AI disabled or unavailable",
        evidence_ids=input_data.evidence_ids,
        data_version=input_data.data_version,
    )

    return RainfallInferenceOutput(
        severity=sev_b,
        trend=trend_b,
        confidence=conf_b,
        expected_intensity_band_mm_h=band_b,
        summary=sum_b,
        key_factors=fact_b,
        recommended_action=act_b,
        evidence_ids=input_data.evidence_ids,
        numerical_forecast=numerical_payload,
        provenance=prov,
    )
