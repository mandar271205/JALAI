"""Truthful audit provenance generation for JalRakshak AI Decision Support.

Ensures that:
- Every inference response contains complete internal traceability
- Numerical model origins are never fabricated
- AI provider slots, failovers, and verifier verdicts are truthfully recorded
- Internal provenance is cleanly separated from normal public frontend displays
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jalrakshak_ml.decision_support.schemas import InferenceMode, InferenceProvenance


def create_provenance(
    *,
    source_mode: InferenceMode,
    primary_model_available: bool,
    numerical_model_name: str | None = None,
    numerical_model_version: str | None = None,
    ai_assistance_used: bool = False,
    ai_generation_used: bool = False,
    ai_generator_slot: int | None = None,
    ai_generator_provider: str | None = None,
    ai_generator_model: str | None = None,
    ai_failover_used: bool = False,
    ai_failover_reason: str | None = None,
    ai_verifier_used: bool = False,
    ai_verifier_provider: str | None = None,
    ai_verifier_model: str | None = None,
    ai_verifier_verdict: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    evidence_ids: list[str] | None = None,
    data_version: str | None = None,
) -> InferenceProvenance:
    """Construct a validated and truthful InferenceProvenance object."""
    return InferenceProvenance(
        source_mode=source_mode,
        primary_model_available=primary_model_available,
        numerical_model_name=numerical_model_name,
        numerical_model_version=numerical_model_version,
        ai_assistance_used=ai_assistance_used,
        ai_generation_used=ai_generation_used,
        ai_generator_slot=ai_generator_slot,
        ai_generator_provider=ai_generator_provider,
        ai_generator_model=ai_generator_model,
        ai_failover_used=ai_failover_used,
        ai_failover_reason=ai_failover_reason,
        ai_verifier_used=ai_verifier_used,
        ai_verifier_provider=ai_verifier_provider,
        ai_verifier_model=ai_verifier_model,
        ai_verifier_verdict=ai_verifier_verdict,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        evidence_ids=list(evidence_ids or []),
        data_version=data_version,
        generated_at=datetime.now(UTC).isoformat(),
    )


def sanitize_provenance_for_frontend(provenance: InferenceProvenance) -> dict[str, Any]:
    """Strip low-level provider/model names if an internal provenance dictionary is passed to public layers."""
    prov_dict = provenance.model_dump()
    # Mask provider details from public visibility
    prov_dict.pop("ai_generator_provider", None)
    prov_dict.pop("ai_generator_model", None)
    prov_dict.pop("ai_verifier_provider", None)
    prov_dict.pop("ai_verifier_model", None)
    return prov_dict
