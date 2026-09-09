import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.ml.circuit_breaker import CircuitBreaker
from app.integrations.ml.provider import MLProvider, StubMLProvider

logger = logging.getLogger("ml.http_client")


class HttpMLProvider(MLProvider):
    """
    HTTP Client for ML Subteam Internal Inference Service.
    Strict architectural boundary: NEVER imports PyTorch or model code.
    Includes timeout, retry, circuit breaker, and automatic fallback to StubMLProvider.
    """

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        timeout_seconds: float = 5.0,
        fallback_stub: StubMLProvider | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.ML_SERVICE_URL
        self.auth_token = auth_token or settings.ML_SERVICE_TOKEN
        self.timeout = timeout_seconds
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=30.0)
        self.stub_fallback = fallback_stub or StubMLProvider()
        self.transport = transport

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post_with_resilience(
        self, path: str, payload: dict[str, Any], fallback_callable
    ) -> Any:
        if not self.circuit_breaker.can_execute():
            logger.warning(f"ML Circuit breaker OPEN. Fast-falling back to stub for path: {path}")
            data = await fallback_callable()
            if isinstance(data, dict):
                data["is_fallback"] = True
                data["is_degraded"] = True
                data["fallback_reason"] = "circuit_breaker_open"
            return data

        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        max_retries = 2

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                    res = await client.post(url, json=payload, headers=self._get_headers())
                    if res.status_code == 200:
                        self.circuit_breaker.record_success()
                        live_data = res.json()
                        if isinstance(live_data, dict) and "is_fallback" not in live_data:
                            live_data["is_fallback"] = False
                        return live_data
                    logger.warning(f"ML service error ({res.status_code}) on attempt {attempt}")
            except Exception as e:
                logger.warning(f"ML request error on attempt {attempt} for {url}: {e}")

        # Trip circuit breaker and fallback
        self.circuit_breaker.record_failure()
        logger.warning(
            f"ML call failed after {max_retries} attempts. Returning deterministic stub."
        )
        fallback_data = await fallback_callable()
        if isinstance(fallback_data, dict):
            fallback_data["is_fallback"] = True
            fallback_data["is_degraded"] = True
            fallback_data["fallback_reason"] = "ml_service_offline_or_error"
        return fallback_data

    async def get_nowcast_manifest(self) -> dict[str, Any]:
        return await self._post_with_resilience(
            "/internal/ml/nowcast", {}, self.stub_fallback.get_nowcast_manifest
        )

    async def get_inundation_manifest(self) -> dict[str, Any]:
        return await self._post_with_resilience(
            "/internal/ml/inundation", {}, self.stub_fallback.get_inundation_manifest
        )

    async def get_risk_cells(
        self, bbox: str | None = None, valid_time: str | None = None
    ) -> list[dict[str, Any]]:
        async def fallback():
            return await self.stub_fallback.get_risk_cells(bbox=bbox, valid_time=valid_time)

        payload = {"bbox": bbox, "valid_time": valid_time}
        result = await self._post_with_resilience("/internal/ml/risk-assessment", payload, fallback)
        if isinstance(result, dict) and "cells" in result:
            return result["cells"]
        elif isinstance(result, list):
            return result
        return await fallback()

    async def verify_report(
        self, report_id: str, image_url: str | None, description: str | None
    ) -> dict[str, Any]:
        async def fallback():
            return await self.stub_fallback.verify_report(report_id, image_url, description)

        payload = {"report_id": report_id, "image_url": image_url, "description": description}
        return await self._post_with_resilience("/internal/ml/verify-report", payload, fallback)
