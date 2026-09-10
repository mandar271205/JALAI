"""Groq Multimodal Vision Service for JalRakshak Citizen Visual Evidence Corroboration.

Provider: Groq
Vision Model: qwen/qwen3.8-27b (or qwen/qwen3.6-27b)
Role: CITIZEN_VISUAL_EVIDENCE (Auxiliary Signal, NOT Ground Truth)

Scientific Sanctity Mandate:
- Visual evidence is an auxiliary corroboration signal, NOT ground truth.
- `exact_depth_m` MUST ALWAYS be None (null). Visual AI cannot measure metric depth from uncalibrated 2D monocular photos.
- Graceful degradation: Any network timeout, rate limit, or invalid response falls back to an explicit safe fallback object.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("jalrakshak.integrations.ai.vision")


class VisualCorroborationResult(BaseModel):
    water_visible: bool = False
    scene_type: str = "unknown"
    visual_severity: str = "UNKNOWN"  # NONE, LOW, MODERATE, HIGH, CRITICAL, UNKNOWN
    road_passability: str = "UNKNOWN"  # LIKELY_PASSABLE, LIKELY_IMPAIRED, UNKNOWN
    drain_overflow_visible: bool = False
    vehicle_impact_visible: bool = False
    building_impact_visible: bool = False
    image_quality: str = "FAIR"  # GOOD, FAIR, POOR
    visual_support_score: float = Field(default=0.0, ge=0.0, le=1.0)
    exact_depth_m: None = None  # Strict scientific mandate: ALWAYS None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_summary: str = ""
    observations: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    is_fallback: bool = False
    model_version: str = "qwen/qwen3.8-27b"
    warnings: list[str] = Field(default_factory=list)


VISION_SYSTEM_PROMPT = """You are JalRakshak Visual Corroboration Engine, an auxiliary AI signal analyzer for flood emergency operations.
Analyze this citizen photograph for flood or waterlogging evidence.

Return ONLY a valid JSON object with the following schema:
{
  "water_visible": boolean,
  "scene_type": "road_waterlogging" | "river_overflow" | "dry_road" | "indoor_flooding" | "unknown",
  "visual_severity": "NONE" | "LOW" | "MODERATE" | "HIGH" | "CRITICAL" | "UNKNOWN",
  "road_passability": "LIKELY_PASSABLE" | "LIKELY_IMPAIRED" | "UNKNOWN",
  "drain_overflow_visible": boolean,
  "vehicle_impact_visible": boolean,
  "building_impact_visible": boolean,
  "image_quality": "GOOD" | "FAIR" | "POOR",
  "visual_support_score": float between 0.0 and 1.0,
  "confidence": float between 0.0 and 1.0,
  "evidence_summary": string,
  "observations": [string],
  "unsupported_claims": [string],
  "exact_depth_m": null
}

STRICT MANDATES:
1. exact_depth_m MUST BE null. Monocular uncalibrated consumer images cannot determine exact physical water depth in meters.
2. Visual evidence is corroborative, not authoritative ground truth.
3. Be objective. If water is not visible or scene is dry, set water_visible to false and visual_severity to "NONE".
4. Do not include markdown code block syntax (like ```json) if possible, or keep it strictly parseable.
"""


class GroqVisionService:
    """Multimodal Vision Service calling Groq API using qwen/qwen3.8-27b."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.GROQ_API_KEY
        self.base_url = (base_url or settings.GROQ_BASE_URL).rstrip("/")
        self.model = model or getattr(settings, "AI_VISION_MODEL", "qwen/qwen3.8-27b")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.enabled = getattr(settings, "AI_VISION_ENABLED", True)

    def _fallback_result(self, reason: str) -> dict[str, Any]:
        return {
            "water_visible": False,
            "scene_type": "unknown",
            "visual_severity": "UNKNOWN",
            "road_passability": "UNKNOWN",
            "drain_overflow_visible": False,
            "vehicle_impact_visible": False,
            "building_impact_visible": False,
            "image_quality": "POOR",
            "visual_support_score": 0.0,
            "exact_depth_m": None,
            "confidence": 0.0,
            "evidence_summary": f"Vision analysis fallback: {reason}",
            "observations": [],
            "unsupported_claims": [],
            "is_fallback": True,
            "model_version": self.model,
            "warnings": [
                f"VISION FALLBACK: {reason}. Visual corroboration unavailable; defaulting to neutral safety stance."
            ],
        }

    def _clean_json_response(self, text: str) -> str:
        """Strip markdown ticks or think tags from model completion."""
        # Remove <think>...</think> tags if model emits them
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    async def analyze_image(
        self,
        image_bytes: bytes | None = None,
        image_url: str | None = None,
        image_b64: str | None = None,
        mime_type: str = "image/jpeg",
        user_context: str | None = None,
    ) -> dict[str, Any]:
        """Analyze a photograph using Groq multimodal vision model.

        Returns verified VisualCorroborationResult dict with exact_depth_m=None.
        """
        if not self.enabled:
            return self._fallback_result("AI Vision is disabled in settings")

        if not self.api_key or self.api_key.startswith("CHANGE_ME"):
            return self._fallback_result("GROQ_API_KEY is missing or unconfigured")

        # Resolve image representation
        data_url = ""
        if image_b64:
            if image_b64.startswith("data:"):
                data_url = image_b64
            else:
                data_url = f"data:{mime_type};base64,{image_b64}"
        elif image_bytes:
            encoded = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{encoded}"
        elif image_url:
            # If public HTTP(S) URL, Groq allows direct URL or we can fetch & base64
            if image_url.startswith("http://") or image_url.startswith("https://"):
                data_url = image_url
            else:
                return self._fallback_result(f"Invalid image URL scheme: {image_url}")
        else:
            return self._fallback_result("No image content or URL provided for vision analysis")

        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": f"{VISION_SYSTEM_PROMPT}\n\nContext from citizen report: {user_context or 'None'}"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": 0.1,
            "max_tokens": 500,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.warning(
                        "Groq vision returned status %d: %s", resp.status_code, resp.text[:200]
                    )
                    return self._fallback_result(f"Groq vision HTTP {resp.status_code}")

                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                cleaned = self._clean_json_response(content)
                parsed = json.loads(cleaned)

                # Strictly enforce exact_depth_m is None
                parsed["exact_depth_m"] = None
                parsed["is_fallback"] = False
                parsed["model_version"] = self.model
                parsed.setdefault("warnings", [])

                # Validate with Pydantic model
                verified = VisualCorroborationResult.model_validate(parsed)
                return verified.model_dump()

        except json.JSONDecodeError as err:
            logger.warning("Failed to parse Groq vision JSON: %s", err)
            return self._fallback_result("Model produced non-JSON output")
        except httpx.TimeoutException:
            logger.warning("Groq vision request timed out after %.1fs", self.timeout_seconds)
            return self._fallback_result("Network timeout contacting Groq API")
        except Exception as exc:
            logger.error("Unexpected error in Groq vision analysis: %s", exc)
            return self._fallback_result(f"Unexpected vision error: {str(exc)[:100]}")


_vision_service_instance: GroqVisionService | None = None


def get_vision_service() -> GroqVisionService:
    global _vision_service_instance
    if _vision_service_instance is None:
        _vision_service_instance = GroqVisionService()
    return _vision_service_instance
