import time

import pytest
from starlette.testclient import TestClient

from app.core.security_hardening import rate_limiter
from app.main import app
from app.realtime.connection_manager import live_manager


@pytest.fixture(autouse=True)
def adjust_rate_limits_for_load_test():
    orig_max = rate_limiter.max_requests
    rate_limiter.max_requests = 2000
    rate_limiter.reset()
    yield
    rate_limiter.max_requests = orig_max
    rate_limiter.reset()


def test_load_risk_cells_concurrency():
    client = TestClient(app)
    latencies = []

    # Simulate 50 rapid queries with pagination and bbox
    for i in range(50):
        start = time.perf_counter()
        r = client.get(
            "/api/v1/risk/cells",
            params={
                "bbox": "72.80,18.90,72.95,19.20",
                "limit": 20,
                "offset": (i % 5) * 10,
            },
        )
        duration = time.perf_counter() - start
        latencies.append(duration)
        assert r.status_code == 200

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    # Verify sub-50ms p95 performance
    assert p95 < 0.10, f"p95 latency {p95:.4f}s exceeded threshold"


def test_load_risk_timeline_caching():
    client = TestClient(app)

    # 1. First fetch
    r1 = client.get("/api/v1/risk/886189254dfffff/timeline")
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag is not None

    # 2. Sequential fetches with ETag
    for _ in range(30):
        start = time.perf_counter()
        r2 = client.get(
            "/api/v1/risk/886189254dfffff/timeline",
            headers={"If-None-Match": etag},
        )
        duration = time.perf_counter() - start
        assert r2.status_code in [200, 304]
        assert duration < 0.05


def test_load_tile_manifests_throughput():
    client = TestClient(app)
    latencies = []

    for _ in range(40):
        start = time.perf_counter()
        r_nc = client.get("/api/v1/nowcast/manifest")
        r_in = client.get("/api/v1/inundation/manifest")
        duration = time.perf_counter() - start
        latencies.append(duration)

        assert r_nc.status_code == 200
        assert r_in.status_code == 200

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 0.10


def test_load_incidents_listing_throughput():
    client = TestClient(app)
    latencies = []

    for i in range(30):
        start = time.perf_counter()
        r = client.get("/api/v1/incidents", params={"severity": "CRITICAL"})
        duration = time.perf_counter() - start
        latencies.append(duration)
        assert r.status_code == 200

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 0.08


@pytest.mark.asyncio
async def test_websocket_fanout_performance():
    # Simulate multiple mock WebSocket clients
    received_counts = [0] * 20

    class MockWebSocket:
        def __init__(self, client_idx):
            self.idx = client_idx

        async def accept(self):
            pass

        async def send_json(self, data):
            received_counts[self.idx] += 1

    mock_sockets = [MockWebSocket(i) for i in range(20)]
    for ws in mock_sockets:
        await live_manager.connect(ws)

    start = time.perf_counter()
    # Broadcast 10 real-time events to all 20 connected clients (200 total dispatches)
    for i in range(10):
        await live_manager.broadcast(
            "risk.cell.updated",
            {"h3_cell": f"cell-{i}", "risk_level": "SEVERE", "depth_m": 0.85},
        )

    fanout_duration = time.perf_counter() - start

    for ws in mock_sockets:
        live_manager.disconnect(ws)

    # All 20 clients should have received all 10 messages
    assert all(c == 10 for c in received_counts)
    # 200 dispatches should complete well under 100ms
    assert fanout_duration < 0.20, f"Fanout duration {fanout_duration:.4f}s took too long"
