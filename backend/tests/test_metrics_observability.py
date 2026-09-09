from starlette.testclient import TestClient

from app.core.sentry import sentry_before_send
from app.core.telemetry import get_current_trace_id, set_current_trace_id
from app.main import app


def test_prometheus_metrics_endpoint_exports_all_domains():
    client = TestClient(app)
    # Generate some traffic
    client.get("/health")
    client.get("/api/v1/weather/current")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    # 1. HTTP Traffic metrics
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text
    assert "http_active_requests" in text

    # 2. Ingestion and source lag
    assert "weather_source_lag_seconds" in text
    assert "weather_ingestion_failures_total" in text

    # 3. Model operations
    assert "ml_inference_duration_seconds" in text

    # 4. Celery and queues
    assert "celery_queue_depth" in text

    # 5. DB pool state
    assert "db_pool_connections" in text


def test_sentry_pii_and_secret_scrubbing():
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer eyJhbGciOiJIUzI1Ni.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
                "cookie": "sessionid=xyz123",
                "x-api-key": "secret-api-key-999",
                "user-agent": "Mozilla/5.0",
            },
            "data": {
                "password": "SuperSecretPassword123!",
                "citizen_name": "Aarav Sharma",
                "aadhaar": "9876 5432 1098",
                "phone": "+91-9876543210",
                "photo": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD...",
            },
        },
        "extra": {
            "token": "sensitive-token-val",
            "metadata": {"nested_phone": "9876543210"},
        },
    }

    scrubbed = sentry_before_send(event, {})
    headers = scrubbed["request"]["headers"]
    data = scrubbed["request"]["data"]
    extra = scrubbed["extra"]

    # Assert headers redacted
    assert headers["authorization"] == "[REDACTED]"
    assert headers["cookie"] == "[REDACTED]"
    assert headers["x-api-key"] == "[REDACTED]"
    assert headers["user-agent"] == "Mozilla/5.0"

    # Assert sensitive data redacted
    assert data["password"] == "[SECRET_REDACTED]"
    assert "9876 5432 1098" not in str(data["aadhaar"])
    assert "9876543210" not in str(data["phone"])
    assert data["photo"] == "[IMAGE_DATA_REDACTED]"

    # Assert extra contexts redacted
    assert extra["token"] == "[SECRET_REDACTED]"
    assert "9876543210" not in str(extra["metadata"]["nested_phone"])


def test_unified_trace_id_propagation():
    client = TestClient(app)
    custom_trace_id = "test-custom-trace-uuid-12345"
    resp = client.get("/health", headers={"X-Trace-Id": custom_trace_id})

    assert resp.status_code == 200
    assert resp.headers["X-Trace-Id"] == custom_trace_id

    # Test ContextVar trace getter and setter
    set_current_trace_id("worker-trace-777")
    assert get_current_trace_id() == "worker-trace-777"
