import pytest

from app.integrations.ml.circuit_breaker import CircuitBreaker, CircuitState
from app.integrations.ml.http_provider import HttpMLProvider
from app.integrations.ml.provider import StubMLProvider


@pytest.mark.asyncio
async def test_circuit_breaker_tripping_and_fallback():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=5.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # Record 1st failure
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # Record 2nd failure -> trips to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


@pytest.mark.asyncio
async def test_http_ml_provider_fallback_to_stub_when_service_unreachable():
    # Point provider to unreachable dummy URL to test fallback
    provider = HttpMLProvider(
        base_url="http://127.0.0.1:59999",
        auth_token="test-token",
        timeout_seconds=0.5,
        fallback_stub=StubMLProvider(),
    )

    # 1. Nowcast fallback
    nowcast = await provider.get_nowcast_manifest()
    assert "manifest_id" in nowcast
    assert "cog_url" in nowcast

    # 2. Inundation fallback
    inundation = await provider.get_inundation_manifest()
    assert "depth_cog_url" in inundation

    # 3. Risk cells fallback
    cells = await provider.get_risk_cells()
    assert len(cells) > 0

    # 4. Report verification fallback
    verif = await provider.verify_report("rep-resilience-01", "http://photo.jpg", "flood")
    assert verif["verification_status"] == "AI_VERIFIED"
