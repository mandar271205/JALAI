"""Three-Model Provider Router and Orchestrator for JalRakshak AI Decision Support.

Execution Hierarchy:
1. Model 1 (Groq GPT-OSS-120B): Primary Generator
2. Model 2 (NVIDIA Nemotron 3.5 Lightning): Fast Failover
3. Model 3 (NVIDIA Nemotron 3 Ultra): Heavy Verifier / Judge (invoked ONLY on high-risk/conflict triggers)

Includes:
- Evidence content-hash SHA-256 TTL caching
- Health tracking for each provider/model slot
- Graceful degradation to deterministic domain fallbacks
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from jalrakshak_ml.decision_support.groq_provider import GroqProvider
from jalrakshak_ml.decision_support.nvidia_provider import NvidiaNIMProvider
from jalrakshak_ml.decision_support.provider_base import LLMProvider
from jalrakshak_ml.decision_support.schemas import (
    FloodCandidateResult,
    FloodInferenceInput,
    RainfallCandidateResult,
    RainfallInferenceInput,
    SeverityLevel,
    VerifierInput,
    VerifierOutput,
)

logger = logging.getLogger("jalrakshak.decision_support.router")


class ProviderHealthTracker:
    """Tracks runtime availability, error rates, and latency for AI slots."""

    def __init__(self):
        self.stats: dict[str, dict[str, Any]] = {
            "slot_1_groq": {"success": 0, "failures": 0, "last_error": None, "last_success_ts": None},
            "slot_2_nvidia": {"success": 0, "failures": 0, "last_error": None, "last_success_ts": None},
            "slot_3_ultra": {"success": 0, "failures": 0, "last_error": None, "last_success_ts": None},
        }

    def record_success(self, slot_key: str):
        if slot_key in self.stats:
            self.stats[slot_key]["success"] += 1
            self.stats[slot_key]["last_success_ts"] = time.time()
            self.stats[slot_key]["last_error"] = None

    def record_failure(self, slot_key: str, error_msg: str):
        if slot_key in self.stats:
            self.stats[slot_key]["failures"] += 1
            self.stats[slot_key]["last_error"] = error_msg[:150]


class ProviderRouter:
    """Orchestrates 3-model inference with fast failover and selective heavy verification."""

    def __init__(
        self,
        llm1: LLMProvider | None = None,
        llm2: LLMProvider | None = None,
        llm3: LLMProvider | None = None,
        cache_ttl_seconds: float = 120.0,
    ):
        self.ai_enabled = os.getenv("AI_INFERENCE_ENABLED", "true").lower() in ("true", "1", "yes")

        # Slot 1: Primary Generator (Groq)
        self.llm1 = llm1 or GroqProvider()
        # Slot 2: Secondary Generator (NVIDIA Lightning)
        self.llm2 = llm2 or NvidiaNIMProvider(role="secondary_generator")
        # Slot 3: Heavy Verifier (NVIDIA Ultra)
        self.llm3 = llm3 or NvidiaNIMProvider(role="heavy_verifier")

        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self.health = ProviderHealthTracker()

        # Configurable verification policies
        self.verify_enabled = os.getenv("AI_VERIFIER_ENABLED", "true").lower() in ("true", "1", "yes")
        self.verify_high_risk = os.getenv("AI_VERIFY_HIGH_RISK", "true").lower() in ("true", "1", "yes")
        self.verify_severe_risk = os.getenv("AI_VERIFY_SEVERE_RISK", "true").lower() in ("true", "1", "yes")
        self.verify_disagreement = os.getenv("AI_VERIFY_DISAGREEMENT", "true").lower() in ("true", "1", "yes")
        self.verify_low_support = os.getenv("AI_VERIFY_LOW_SUPPORT", "true").lower() in ("true", "1", "yes")
        self.verifier_min_support = float(os.getenv("AI_VERIFIER_MIN_SUPPORT", "0.65"))

    def _compute_hash(self, payload: dict[str, Any]) -> str:
        """Compute SHA-256 hash of deterministic payload."""
        data_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def _get_from_cache(self, key: str) -> Any | None:
        if key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts <= self.cache_ttl:
                return val
            del self._cache[key]
        return None

    def _put_cache(self, key: str, val: Any) -> None:
        self._cache[key] = (time.time(), val)

    def should_trigger_verifier(
        self,
        severity_or_risk: SeverityLevel,
        confidence: float,
        had_disagreement: bool = False,
        explicit_verify: bool = False,
    ) -> bool:
        """Determine if Model 3 (Nemotron Ultra) verification should run."""
        if not self.verify_enabled:
            return False
        if explicit_verify:
            return True
        if self.verify_severe_risk and severity_or_risk == SeverityLevel.SEVERE:
            return True
        if self.verify_high_risk and severity_or_risk == SeverityLevel.HIGH:
            return True
        if self.verify_disagreement and had_disagreement:
            return True
        return bool(self.verify_low_support and confidence < self.verifier_min_support)


    async def route_rainfall_inference(
        self,
        input_data: RainfallInferenceInput,
        has_numerical_model: bool = False,
    ) -> tuple[RainfallCandidateResult | None, int | None, str | None, str | None, bool, str | None, VerifierOutput | None]:
        """Execute Model 1 -> Model 2 failover -> selective Model 3 verification for rainfall."""
        if not self.ai_enabled:
            return None, None, None, None, False, "ai_disabled", None

        cache_key = f"rain_{self._compute_hash(input_data.model_dump())}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        candidate: RainfallCandidateResult | None = None
        gen_slot: int | None = None
        gen_provider: str | None = None
        gen_model: str | None = None
        failover_used: bool = False
        failover_reason: str | None = None
        verifier_result: VerifierOutput | None = None

        # 1. Attempt Model 1 (Groq)
        try:
            candidate = await self.llm1.generate_rainfall_inference(input_data)
            gen_slot = 1
            gen_provider = self.llm1.name
            gen_model = self.llm1.model_id
            self.health.record_success("slot_1_groq")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Model 1 (Groq) failed: {e}. Initiating fast failover to Model 2.")
            self.health.record_failure("slot_1_groq", str(e))
            failover_used = True
            failover_reason = f"Slot 1 failed: {e}"

            # 2. Fast Failover to Model 2 (NVIDIA Lightning)
            try:
                candidate = await self.llm2.generate_rainfall_inference(input_data)
                gen_slot = 2
                gen_provider = self.llm2.name
                gen_model = self.llm2.model_id
                self.health.record_success("slot_2_nvidia")
            except Exception as e2:  # noqa: BLE001
                logger.error(f"Model 2 (NVIDIA Lightning) failed: {e2}. Both AI generators unavailable.")
                self.health.record_failure("slot_2_nvidia", str(e2))
                failover_reason = f"All AI generators failed. Slot 1: {e} | Slot 2: {e2}"
                return None, None, None, None, True, failover_reason, None

        # 3. Check if Model 3 verification is required
        if candidate is not None:
            had_disagreement = False
            if has_numerical_model and input_data.rainfall_mm_h:
                max_rate = max(input_data.rainfall_mm_h)
                if max_rate >= 35.0 and candidate.severity in (SeverityLevel.LOW, SeverityLevel.MODERATE):
                    had_disagreement = True

            if self.should_trigger_verifier(
                candidate.severity, candidate.confidence, had_disagreement=had_disagreement
            ):
                logger.info(f"Triggering Model 3 (Nemotron Ultra) verification for rainfall candidate (severity={candidate.severity}).")
                ver_input = VerifierInput(
                    domain="rainfall",
                    evidence=input_data.model_dump(),
                    numerical_model_result={"rainfall_mm_h": input_data.rainfall_mm_h} if has_numerical_model else None,
                    candidate_ai_result=candidate.model_dump(),
                    source_mode="MODEL_PLUS_AI" if has_numerical_model else "PROVISIONAL_AI",
                    data_quality=input_data.quality_score,
                    model_confidence=input_data.model_confidence,
                    evidence_ids=input_data.evidence_ids,
                )
                try:
                    verifier_result = await self.llm3.verify_inference(ver_input)
                    self.health.record_success("slot_3_ultra")
                except Exception as e_v:  # noqa: BLE001
                    logger.warning(f"Model 3 verifier failed: {e_v}. Preserving candidate safely.")
                    self.health.record_failure("slot_3_ultra", str(e_v))

        result_tuple = (
            candidate,
            gen_slot,
            gen_provider,
            gen_model,
            failover_used,
            failover_reason,
            verifier_result,
        )
        self._put_cache(cache_key, result_tuple)
        return result_tuple

    async def route_flood_inference(
        self,
        input_data: FloodInferenceInput,
        has_numerical_model: bool = False,
    ) -> tuple[FloodCandidateResult | None, int | None, str | None, str | None, bool, str | None, VerifierOutput | None]:
        """Execute Model 1 -> Model 2 failover -> selective Model 3 verification for flood."""
        if not self.ai_enabled:
            return None, None, None, None, False, "ai_disabled", None

        cache_key = f"flood_{self._compute_hash(input_data.model_dump())}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        candidate: FloodCandidateResult | None = None
        gen_slot: int | None = None
        gen_provider: str | None = None
        gen_model: str | None = None
        failover_used: bool = False
        failover_reason: str | None = None
        verifier_result: VerifierOutput | None = None

        # 1. Attempt Model 1 (Groq)
        try:
            candidate = await self.llm1.generate_flood_inference(input_data)
            gen_slot = 1
            gen_provider = self.llm1.name
            gen_model = self.llm1.model_id
            self.health.record_success("slot_1_groq")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Model 1 (Groq) failed: {e}. Initiating fast failover to Model 2.")
            self.health.record_failure("slot_1_groq", str(e))
            failover_used = True
            failover_reason = f"Slot 1 failed: {e}"

            # 2. Fast Failover to Model 2 (NVIDIA Lightning)
            try:
                candidate = await self.llm2.generate_flood_inference(input_data)
                gen_slot = 2
                gen_provider = self.llm2.name
                gen_model = self.llm2.model_id
                self.health.record_success("slot_2_nvidia")
            except Exception as e2:  # noqa: BLE001
                logger.error(f"Model 2 (NVIDIA Lightning) failed: {e2}. Both AI generators unavailable.")
                self.health.record_failure("slot_2_nvidia", str(e2))
                failover_reason = f"All AI generators failed. Slot 1: {e} | Slot 2: {e2}"
                return None, None, None, None, True, failover_reason, None

        # 3. Check if Model 3 verification is required
        if candidate is not None:
            had_disagreement = False
            if has_numerical_model and input_data.numerical_model_output:
                num_risk = input_data.numerical_model_output.get("risk_level")
                if num_risk and num_risk.upper() != candidate.risk_level.value:
                    had_disagreement = True

            if self.should_trigger_verifier(
                candidate.risk_level, candidate.confidence, had_disagreement=had_disagreement
            ):
                logger.info(f"Triggering Model 3 (Nemotron Ultra) verification for flood candidate (risk={candidate.risk_level}).")
                ver_input = VerifierInput(
                    domain="flood",
                    evidence=input_data.model_dump(),
                    numerical_model_result=input_data.numerical_model_output if has_numerical_model else None,
                    candidate_ai_result=candidate.model_dump(),
                    source_mode="MODEL_PLUS_AI" if has_numerical_model else "PROVISIONAL_AI",
                    data_quality=input_data.quality_score,
                    model_confidence=input_data.model_confidence,
                    evidence_ids=input_data.evidence_ids,
                )
                try:
                    verifier_result = await self.llm3.verify_inference(ver_input)
                    self.health.record_success("slot_3_ultra")
                except Exception as e_v:  # noqa: BLE001
                    logger.warning(f"Model 3 verifier failed: {e_v}. Preserving candidate safely.")
                    self.health.record_failure("slot_3_ultra", str(e_v))

        result_tuple = (
            candidate,
            gen_slot,
            gen_provider,
            gen_model,
            failover_used,
            failover_reason,
            verifier_result,
        )
        self._put_cache(cache_key, result_tuple)
        return result_tuple
