"""Deterministic arbitration engine and anti-hallucination gates for JalRakshak AI.

Strictly enforces:
1. Numerical Supremacy: Validated numerical/physics models always override LLM output.
2. Anti-Hallucination Flood Gate: depth_m MUST remain null unless genuine numerical depth output exists.
3. Anti-Hallucination Rain Gate: Expected rainfall intensity bounds cannot exceed evidence bounds without derivation.
4. Prohibition of LLM Majority Overrule: 2 LLMs cannot vote to override numerical evidence.
5. Verifier Verdict Enforcement: Mapping ACCEPT, DOWNGRADE, REJECT, and INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

import logging

from jalrakshak_ml.decision_support.schemas import (
    FloodCandidateResult,
    FloodInferenceInput,
    IntensityBand,
    RainfallCandidateResult,
    RainfallInferenceInput,
    SeverityLevel,
    VerifierOutput,
    VerifierVerdict,
)

logger = logging.getLogger("jalrakshak.decision_support.arbitration")

# Forbidden fabricated terms that indicate hallucinated ground truth or sensors
FORBIDDEN_FABRICATED_TOKENS = [
    "observed_depth_gauge",
    "calibrated_depth_truth",
    "insat_3d_direct_telemetry",
    "imd_doppler_direct_feed",
    "ground_truth_water_gauge",
]


def audit_anti_hallucination_text(text: str) -> list[str]:
    """Detect fabricated sensors or non-existent ground truth claims in text."""
    lowered = text.lower()
    found = []
    for token in FORBIDDEN_FABRICATED_TOKENS:
        if token in lowered:
            found.append(token)
    return found


def arbitrate_rainfall(
    input_data: RainfallInferenceInput,
    candidate: RainfallCandidateResult,
    has_numerical_model: bool,
    verifier_result: VerifierOutput | None = None,
) -> tuple[SeverityLevel, float, IntensityBand, str, list[str], list[str], str | None]:
    """Arbitrate rainfall inference candidate against numerical evidence and verifier."""
    severity = candidate.severity
    confidence = candidate.confidence
    intensity_band = IntensityBand(
        min=candidate.expected_intensity_band_mm_h.min,
        max=candidate.expected_intensity_band_mm_h.max,
    )
    summary = candidate.summary
    key_factors = list(candidate.key_factors)
    conflicts: list[str] = []
    fallback_reason: str | None = None

    # Calculate evidence bounds for rainfall
    evidence_rain_rates: list[float] = []
    if input_data.rainfall_mm_h:
        evidence_rain_rates.extend([float(r) for r in input_data.rainfall_mm_h if r is not None])
    if input_data.latest_observation_mm_h is not None:
        evidence_rain_rates.append(float(input_data.latest_observation_mm_h))
    if input_data.persistence_baseline_mm_h is not None:
        evidence_rain_rates.append(float(input_data.persistence_baseline_mm_h))
    if input_data.gfs_context and "precipitation_mm_h" in input_data.gfs_context:
        try:
            evidence_rain_rates.append(float(input_data.gfs_context["precipitation_mm_h"]))
        except (ValueError, TypeError):
            pass

    max_evidence_rain = max(evidence_rain_rates) if evidence_rain_rates else None

    # Anti-hallucination Gate 1: Check text for forbidden claims
    hallucinations = audit_anti_hallucination_text(summary) + audit_anti_hallucination_text(" ".join(key_factors))
    if hallucinations:
        logger.warning(f"Rainfall candidate contains hallucinated tokens: {hallucinations}")
        conflicts.append(f"Forbidden hallucinated references: {hallucinations}")
        confidence = min(confidence, 0.40)

    # Anti-hallucination Gate 2: Rain rate bounds enforcement
    if max_evidence_rain is not None and intensity_band.max is not None:
        # Allow reasonable upper envelope (up to 2.0x max evidence or +15mm/h margin for convective amplification)
        permitted_upper = max(max_evidence_rain * 2.0, max_evidence_rain + 15.0)
        if intensity_band.max > permitted_upper:
            logger.warning(
                f"Candidate rainfall max {intensity_band.max} exceeds evidence bound {permitted_upper}. Clamping."
            )
            conflicts.append(
                f"Candidate intensity {intensity_band.max} mm/h exceeded evidence bounds; clamped to {permitted_upper:.1f} mm/h"
            )
            intensity_band.max = round(permitted_upper, 1)

    # Numerical Model Supremacy Gate
    if has_numerical_model and input_data.rainfall_mm_h:
        max_model_rate = max(input_data.rainfall_mm_h)
        # Determine expected numerical severity
        if max_model_rate >= 65.0:
            expected_sev = SeverityLevel.SEVERE
        elif max_model_rate >= 35.0:
            expected_sev = SeverityLevel.HIGH
        elif max_model_rate >= 10.0:
            expected_sev = SeverityLevel.MODERATE
        else:
            expected_sev = SeverityLevel.LOW

        if severity != expected_sev:
            logger.warning(
                f"AI candidate severity ({severity}) disagreed with numerical model ({expected_sev}). "
                "Numerical model is authoritative."
            )
            conflicts.append(f"Numerical model indicated {expected_sev}, overriding AI candidate {severity}")
            severity = expected_sev

    # Verifier Verdict Processing (Model 3)
    if verifier_result is not None:
        if verifier_result.verdict == VerifierVerdict.DOWNGRADE:
            logger.info(f"Model 3 verifier requested DOWNGRADE: {verifier_result.reason}")
            if verifier_result.recommended_severity:
                severity = verifier_result.recommended_severity
            elif severity == SeverityLevel.SEVERE:
                severity = SeverityLevel.HIGH
            elif severity == SeverityLevel.HIGH:
                severity = SeverityLevel.MODERATE
            confidence = min(confidence, verifier_result.evidence_support_score, 0.65)
            conflicts.append(f"Downgraded by Model 3 Verifier: {verifier_result.reason}")

        elif verifier_result.verdict == VerifierVerdict.REJECT:
            logger.warning(f"Model 3 verifier REJECTED candidate: {verifier_result.reason}")
            fallback_reason = f"Verifier rejected: {verifier_result.reason}"
            conflicts.extend(verifier_result.identified_conflicts)
            conflicts.extend(verifier_result.unsupported_claims)

        elif verifier_result.verdict == VerifierVerdict.INSUFFICIENT_EVIDENCE:
            logger.info("Model 3 verifier flagged INSUFFICIENT_EVIDENCE")
            confidence = min(confidence, 0.35)
            fallback_reason = "Verifier indicated insufficient evidence"

    return severity, confidence, intensity_band, summary, key_factors, conflicts, fallback_reason


def arbitrate_flood(
    input_data: FloodInferenceInput,
    candidate: FloodCandidateResult,
    has_numerical_model: bool,
    verifier_result: VerifierOutput | None = None,
) -> tuple[SeverityLevel, float, float | None, str, list[str], list[str], str | None]:
    """Arbitrate flood inference candidate against physical evidence and verifier."""
    risk_level = candidate.risk_level
    confidence = candidate.confidence
    summary = candidate.summary
    dominant_factors = list(candidate.dominant_factors)
    conflicts: list[str] = []
    fallback_reason: str | None = None

    # Anti-hallucination Gate 1: Check text for forbidden claims
    hallucinations = audit_anti_hallucination_text(summary) + audit_anti_hallucination_text(" ".join(dominant_factors))
    if hallucinations:
        logger.warning(f"Flood candidate contains hallucinated tokens: {hallucinations}")
        conflicts.append(f"Forbidden hallucinated references: {hallucinations}")
        confidence = min(confidence, 0.40)

    # Anti-hallucination Gate 2: Physical Depth Sanctity
    # If no genuine numerical model depth is provided, depth_m MUST be None
    genuine_depth = None
    if has_numerical_model and input_data.numerical_model_output:
        genuine_depth = input_data.numerical_model_output.get("max_depth_m") or input_data.numerical_model_output.get("depth_m")

    if genuine_depth is not None:
        depth_m = float(genuine_depth)
    else:
        # Strictly enforce null depth
        if candidate.depth_m is not None:
            logger.warning(
                f"Candidate fabricated flood depth {candidate.depth_m}m without numerical solver output. Enforcing null."
            )
            conflicts.append(
                f"Candidate fabricated depth {candidate.depth_m}m was rejected. Depth set to null."
            )
        depth_m = None

    # Numerical Model Supremacy Gate
    if has_numerical_model and input_data.numerical_model_output:
        expected_risk = input_data.numerical_model_output.get("risk_level")
        if expected_risk:
            try:
                norm_expected = SeverityLevel(expected_risk.upper())
                if risk_level != norm_expected:
                    logger.warning(
                        f"AI flood risk ({risk_level}) disagreed with physical solver ({norm_expected}). "
                        "Physical solver is authoritative."
                    )
                    conflicts.append(
                        f"Physical solver indicated {norm_expected}, overriding AI candidate {risk_level}"
                    )
                    risk_level = norm_expected
            except (ValueError, AttributeError):
                pass

    # Verifier Verdict Processing (Model 3)
    if verifier_result is not None:
        if verifier_result.verdict == VerifierVerdict.DOWNGRADE:
            logger.info(f"Model 3 verifier requested DOWNGRADE for flood: {verifier_result.reason}")
            if verifier_result.recommended_severity:
                risk_level = verifier_result.recommended_severity
            elif risk_level == SeverityLevel.SEVERE:
                risk_level = SeverityLevel.HIGH
            elif risk_level == SeverityLevel.HIGH:
                risk_level = SeverityLevel.MODERATE
            confidence = min(confidence, verifier_result.evidence_support_score, 0.65)
            conflicts.append(f"Downgraded by Model 3 Verifier: {verifier_result.reason}")

        elif verifier_result.verdict == VerifierVerdict.REJECT:
            logger.warning(f"Model 3 verifier REJECTED flood candidate: {verifier_result.reason}")
            fallback_reason = f"Verifier rejected: {verifier_result.reason}"
            conflicts.extend(verifier_result.identified_conflicts)
            conflicts.extend(verifier_result.unsupported_claims)

        elif verifier_result.verdict == VerifierVerdict.INSUFFICIENT_EVIDENCE:
            logger.info("Model 3 verifier flagged INSUFFICIENT_EVIDENCE for flood")
            confidence = min(confidence, 0.35)
            fallback_reason = "Verifier indicated insufficient evidence"

    return risk_level, confidence, depth_m, summary, dominant_factors, conflicts, fallback_reason
