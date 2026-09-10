"""Flood Unified Inference Layer: Model-First with AI and Deterministic Fallback.

Strictly adheres to:
1. Model-First: Physical solver / validated FNO remains authoritative when available.
2. Depth Sanctity: depth_m MUST remain null unless genuine numerical depth output exists.
3. Provisional AI: When depth model is unavailable, terrain + susceptibility + HxExV powers structured provisional assessment.
4. Truthful provenance: Never attributes LLM output to LISFLOOD-FP or FNO.
"""
from __future__ import annotations

import logging

from jalrakshak_ml.decision_support.arbitration import arbitrate_flood
from jalrakshak_ml.decision_support.provenance import create_provenance
from jalrakshak_ml.decision_support.provider_router import ProviderRouter
from jalrakshak_ml.decision_support.schemas import (
    FloodInferenceInput,
    FloodInferenceOutput,
    InferenceMode,
    SeverityLevel,
)

logger = logging.getLogger("jalrakshak.decision_support.flood")


def derive_deterministic_flood_baseline(input_data: FloodInferenceInput) -> tuple[SeverityLevel, float, float | None, str, list[str], str]:
    """Deterministic rule-based baseline when AI is unavailable or fails."""
    # Check if numerical model provided genuine depth
    genuine_depth = None
    if input_data.numerical_model_output:
        genuine_depth = input_data.numerical_model_output.get("max_depth_m") or input_data.numerical_model_output.get("depth_m")

    # Compute baseline risk from HxExV or susceptibility
    hev = input_data.hev_risk_score
    susc = input_data.susceptibility_score
    rain = input_data.rainfall_forcing_mm_h or 0.0

    score = hev if hev is not None else (susc if susc is not None else (rain / 100.0))

    if score >= 0.75 or rain >= 65.0:
        risk = SeverityLevel.SEVERE
        action = "Deploy rapid rescue units to designated low-lying depressions; issue immediate flood evacuations."
    elif score >= 0.50 or rain >= 35.0:
        risk = SeverityLevel.HIGH
        action = "Position municipal dewatering pumps and erect flood barriers around critical infrastructure."
    elif score >= 0.25 or rain >= 15.0:
        risk = SeverityLevel.MODERATE
        action = "Inspect local culverts and maintain continuous telemetry monitoring."
    else:
        risk = SeverityLevel.LOW
        action = "Normal catchment monitoring; no immediate flood alert required."

    summary = f"Deterministic baseline assessment indicates {risk.value} flood hazard potential derived from topographic and rainfall forcing."
    factors = []
    if input_data.rainfall_forcing_mm_h is not None:
        factors.append(f"Rainfall forcing: {input_data.rainfall_forcing_mm_h:.1f} mm/h")
    if input_data.susceptibility_score is not None:
        factors.append(f"Topographic susceptibility score: {input_data.susceptibility_score:.2f}")
    if input_data.critical_assets:
        factors.append(f"Critical assets exposed: {', '.join(input_data.critical_assets[:3])}")

    return risk, 0.70, genuine_depth, summary, factors, action


async def infer_flood(
    input_data: FloodInferenceInput,
    router: ProviderRouter | None = None,
) -> FloodInferenceOutput:
    """Execute unified model-first flood inference with AI fallback and strict depth safety."""
    active_router = router or ProviderRouter()

    # Determine if numerical model output is genuinely present
    has_numerical_model = bool(
        input_data.numerical_model_output and input_data.model_name
    )

    # Check for complete lack of evidence (Insufficient Evidence)
    has_evidence = (
        has_numerical_model
        or (input_data.rainfall_forcing_mm_h is not None)
        or (input_data.susceptibility_score is not None)
        or (input_data.dem_elevation_m is not None)
        or (input_data.hev_risk_score is not None)
        or (input_data.exposure_score is not None)
    )

    if not has_evidence:
        logger.warning("No numerical model and no geospatial/hydrologic evidence supplied for flood.")
        prov = create_provenance(
            source_mode=InferenceMode.INSUFFICIENT_EVIDENCE,
            primary_model_available=False,
            ai_assistance_used=False,
            fallback_used=True,
            fallback_reason="No numerical model or hydrologic/terrain observations supplied",
            evidence_ids=input_data.evidence_ids,
        )
        return FloodInferenceOutput(
            risk_level=SeverityLevel.LOW,
            confidence=0.10,
            depth_m=None,
            dominant_factors=["Missing topographic elevation data", "Missing rainfall forcing evidence"],
            summary="Insufficient geospatial and hydrologic evidence available to evaluate flood risk.",
            recommended_action="Await DEM raster ingestion or live precipitation forcing telemetry.",
            evidence_ids=input_data.evidence_ids,
            numerical_model_output=None,
            provenance=prov,
        )

    # Route request through Three-Model Router
    candidate, gen_slot, gen_provider, gen_model, failover_used, failover_reason, verifier_res = (
        await active_router.route_flood_inference(input_data, has_numerical_model=has_numerical_model)
    )

    # Case A: AI generation succeeded (Model 1 or Model 2)
    if candidate is not None:
        (
            risk_level,
            confidence,
            depth_m,
            summary,
            dominant_factors,
            _conflicts,
            arbitration_fallback,
        ) = arbitrate_flood(
            input_data,
            candidate,
            has_numerical_model=has_numerical_model,
            verifier_result=verifier_res,
        )

        # If verifier rejected candidate completely, fall back to deterministic baseline
        if arbitration_fallback:
            logger.warning(f"Flood arbitration triggered fallback: {arbitration_fallback}")
            risk_b, conf_b, depth_b, sum_b, fact_b, act_b = derive_deterministic_flood_baseline(input_data)
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
            )
            return FloodInferenceOutput(
                risk_level=risk_b,
                confidence=conf_b,
                depth_m=depth_b,
                dominant_factors=fact_b,
                summary=sum_b,
                recommended_action=act_b,
                evidence_ids=input_data.evidence_ids,
                numerical_model_output=input_data.numerical_model_output,
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
        )

        return FloodInferenceOutput(
            risk_level=risk_level,
            confidence=confidence,
            depth_m=depth_m,
            dominant_factors=dominant_factors,
            summary=summary,
            recommended_action=candidate.recommended_action,
            evidence_ids=input_data.evidence_ids,
            numerical_model_output=input_data.numerical_model_output,
            provenance=prov,
        )

    # Case B: AI was unavailable, disabled, or all providers failed -> Deterministic Fallback
    risk_b, conf_b, depth_b, sum_b, fact_b, act_b = derive_deterministic_flood_baseline(input_data)
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
    )

    return FloodInferenceOutput(
        risk_level=risk_b,
        confidence=conf_b,
        depth_m=depth_b,
        dominant_factors=fact_b,
        summary=sum_b,
        recommended_action=act_b,
        evidence_ids=input_data.evidence_ids,
        numerical_model_output=input_data.numerical_model_output,
        provenance=prov,
    )
