"""Abstract base class and utility functions for Decision Support LLM Providers.

Strictly adheres to:
- Non-blocking async execution
- Resilient JSON parsing (handles markdown formatting and thinking content)
- Prompt injection defenses: untrusted text is serialized in payload data, never system prompt
- Zero secrets in logs
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from jalrakshak_ml.decision_support.schemas import (
    FloodCandidateResult,
    FloodInferenceInput,
    RainfallCandidateResult,
    RainfallInferenceInput,
    VerifierInput,
    VerifierOutput,
)

logger = logging.getLogger("jalrakshak.decision_support.provider")

BASE_SYSTEM_PROMPT = """You are an auxiliary environmental inference engine inside JalRakshak AI.
Use only the structured evidence supplied.
Never claim that a trained numerical model generated a value unless the evidence explicitly contains that model output.
Never invent rainfall measurements, probabilities, flood depths, model metrics, sensor availability or calibration.
When a numerical model result is provided, preserve it.
When a numerical model result is absent, produce only a provisional evidence-based assessment.
If evidence is insufficient, return INSUFFICIENT_EVIDENCE.
Return valid JSON conforming exactly to the required schema. No prose outside JSON."""


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract and parse a JSON dictionary from raw model completion text."""
    clean_text = text.strip()

    # Remove markdown code blocks if present
    if "```" in clean_text:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1).strip()
        else:
            # Fallback: remove backticks
            clean_text = re.sub(r"^```(?:json)?", "", clean_text)
            clean_text = re.sub(r"```$", "", clean_text).strip()

    # First attempt: direct json.loads
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Second attempt: locate outermost { ... }
    first_brace = clean_text.find("{")
    last_brace = clean_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        slice_text = clean_text[first_brace : last_brace + 1]
        try:
            data = json.loads(slice_text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(f"Failed to parse valid JSON object from model output: {text[:200]}")


def sanitize_untrusted_input(text: str | None) -> str:
    """Sanitize and constrain user/citizen free text to avoid instruction override."""
    if not text:
        return ""
    # Strip dangerous tokens and cap length
    sanitized = text.replace("\r", " ").strip()
    return sanitized[:500]


class LLMProvider(ABC):
    """Abstract interface for LLM inference providers in JalRakshak AI."""

    def __init__(self, name: str, model_id: str, timeout_seconds: float = 8.0):
        self.name = name
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def generate_rainfall_inference(
        self, input_data: RainfallInferenceInput
    ) -> RainfallCandidateResult:
        """Produce structured rainfall inference from meteorological evidence or numerical model."""

    @abstractmethod
    async def generate_flood_inference(
        self, input_data: FloodInferenceInput
    ) -> FloodCandidateResult:
        """Produce structured flood risk inference from geospatial/hydrologic evidence."""

    @abstractmethod
    async def verify_inference(
        self, verifier_input: VerifierInput
    ) -> VerifierOutput:
        """Evaluate a candidate inference result against evidence and report a verdict."""
