"""Groq LLM Provider implementation for JalRakshak AI Decision Support (Model 1).

Role: PRIMARY_GENERATOR
Default Model: openai/gpt-oss-120b
Endpoint: https://api.groq.com/openai/v1/chat/completions
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from jalrakshak_ml.decision_support.provider_base import (
    BASE_SYSTEM_PROMPT,
    LLMProvider,
    extract_json_object,
    sanitize_untrusted_input,
)
from jalrakshak_ml.decision_support.schemas import (
    FloodCandidateResult,
    FloodInferenceInput,
    RainfallCandidateResult,
    RainfallInferenceInput,
    VerifierInput,
    VerifierOutput,
)

logger = logging.getLogger("jalrakshak.decision_support.groq")


class GroqProvider(LLMProvider):
    """Groq API provider implementation for Model 1 (Primary Generator)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_id: str | None = None,
        timeout_seconds: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ):
        model = model_id or os.getenv("AI_LLM1_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b"
        super().__init__(name="groq", model_id=model, timeout_seconds=timeout_seconds)
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.base_url = (base_url or os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.transport = transport

    def _get_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post_chat_completion(
        self, system_instruction: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute async HTTP POST to Groq completions endpoint."""
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Groq API error {response.status_code}: {response.text[:200]}"
                )
            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as err:
                raise ValueError(f"Malformed completion response from Groq: {data}") from err
            return extract_json_object(content)

    async def generate_rainfall_inference(
        self, input_data: RainfallInferenceInput
    ) -> RainfallCandidateResult:
        system_prompt = (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Task: Produce structured rainfall inference.\n"
            "Output Schema Keys:\n"
            "- severity: LOW | MODERATE | HIGH | SEVERE\n"
            "- trend: DECREASING | STABLE | INCREASING | UNKNOWN\n"
            "- confidence: float between 0.0 and 1.0\n"
            "- expected_intensity_band_mm_h: {min: float or null, max: float or null}\n"
            "- summary: concise operational summary (string)\n"
            "- key_factors: list of contributing meteorological factors (strings)\n"
            "- recommended_action: operational action recommendation (string)\n"
            "- evidence_ids: list of evidence identifiers referenced (strings)\n\n"
            "Constraint: If numerical rainfall is provided, reflect its severity faithfully without fabricating new numbers."
        )

        payload = input_data.model_dump()
        if input_data.untrusted_user_input:
            payload["citizen_feedback"] = sanitize_untrusted_input(input_data.untrusted_user_input)
            payload.pop("untrusted_user_input", None)

        raw_json = await self._post_chat_completion(system_prompt, payload)
        return RainfallCandidateResult.model_validate(raw_json)

    async def generate_flood_inference(
        self, input_data: FloodInferenceInput
    ) -> FloodCandidateResult:
        system_prompt = (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Task: Produce structured flood risk inference.\n"
            "Output Schema Keys:\n"
            "- risk_level: LOW | MODERATE | HIGH | SEVERE\n"
            "- confidence: float between 0.0 and 1.0\n"
            "- depth_m: null (STRICT MANDATE: MUST be null unless physical depth solver output is provided in input)\n"
            "- dominant_factors: list of dominant risk contributors (strings)\n"
            "- summary: concise operational summary (string)\n"
            "- recommended_action: operational action recommendation (string)\n"
            "- evidence_ids: list of evidence identifiers referenced (strings)\n\n"
            "Constraint: NEVER invent water depth in meters. If no depth model output is given, depth_m MUST be null."
        )

        payload = input_data.model_dump()
        if input_data.untrusted_user_input:
            payload["citizen_feedback"] = sanitize_untrusted_input(input_data.untrusted_user_input)
            payload.pop("untrusted_user_input", None)

        raw_json = await self._post_chat_completion(system_prompt, payload)
        return FloodCandidateResult.model_validate(raw_json)

    async def verify_inference(
        self, verifier_input: VerifierInput
    ) -> VerifierOutput:
        system_prompt = (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Task: Verify candidate inference against structured evidence.\n"
            "Output Schema Keys:\n"
            "- verdict: ACCEPT | REJECT | DOWNGRADE | INSUFFICIENT_EVIDENCE\n"
            "- agreement_score: float between 0.0 and 1.0\n"
            "- evidence_support_score: float between 0.0 and 1.0\n"
            "- identified_conflicts: list of conflicting claims (strings)\n"
            "- unsupported_claims: list of unsupported claims (strings)\n"
            "- recommended_severity: LOW | MODERATE | HIGH | SEVERE or null\n"
            "- reason: explanation of the judgment (string)"
        )

        raw_json = await self._post_chat_completion(system_prompt, verifier_input.model_dump())
        return VerifierOutput.model_validate(raw_json)
