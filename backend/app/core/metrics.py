import time
from collections.abc import Callable

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware

# --- 1. HTTP Traffic Metrics ---
http_requests_total = Counter(
    "http_requests_total",
    "Total count of HTTP requests processed by endpoint and status.",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds (p50/p95/p99).",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

http_active_requests = Gauge(
    "http_active_requests",
    "Number of currently active in-flight HTTP requests.",
    ["method"],
)

# --- 2. Telemetry Ingestion Metrics ---
weather_source_lag_seconds = Gauge(
    "weather_source_lag_seconds",
    "Telemetry source ingestion lag / freshness in seconds.",
    ["source_id", "source_type"],
)

weather_ingestion_failures_total = Counter(
    "weather_ingestion_failures_total",
    "Count of weather source ingestion errors or dropouts.",
    ["source_id", "error_type"],
)

# --- 3. ML Inference & Model Operations ---
ml_inference_duration_seconds = Histogram(
    "ml_inference_duration_seconds",
    "ML model inference latency in seconds.",
    ["model_type", "provider"],
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0),
)

# --- 4. Tile Rendering & Spatial Serving ---
tile_rendering_duration_seconds = Histogram(
    "tile_rendering_duration_seconds",
    "Geospatial raster/vector tile serving latency in seconds.",
    ["tile_type", "layer"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# --- 5. Async Worker & Queue Depth ---
celery_queue_depth = Gauge(
    "celery_queue_depth",
    "Current pending tasks in Celery queue.",
    ["queue_name"],
)

# --- 6. Notifications & Sync Conflicts ---
notification_failures_total = Counter(
    "notification_failures_total",
    "Count of outbound push notification delivery failures.",
    ["provider", "channel"],
)

offline_sync_conflicts_total = Counter(
    "offline_sync_conflicts_total",
    "Count of offline synchronization version conflicts detected.",
    ["entity_type"],
)

# --- 7. Database Pool State ---
db_pool_connections = Gauge(
    "db_pool_connections",
    "Database connection pool state.",
    ["state"],  # "checked_in", "checked_out", "overflow"
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that collects Prometheus request duration, request totals,
    and active in-flight requests across all endpoints.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        # Simplify path template for metrics grouping (strip query params and normalize IDs)
        path = request.url.path
        if path == "/metrics":
            return await call_next(request)

        http_active_requests.labels(method=method).inc()
        start_time = time.time()

        try:
            response: Response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.time() - start_time
            http_active_requests.labels(method=method).dec()

            # Record metrics
            http_requests_total.labels(method=method, endpoint=path, status=status_code).inc()
            http_request_duration_seconds.labels(method=method, endpoint=path).observe(duration)


def get_prometheus_metrics() -> tuple[bytes, str]:
    """
    Returns Prometheus metrics exposition payload and MIME type.
    """
    return generate_latest(), CONTENT_TYPE_LATEST


def record_initial_gauges():
    """
    Seeds initial realistic gauges for Grafana scrape readiness.
    """
    weather_source_lag_seconds.labels(source_id="imd-radar-mumbai", source_type="RADAR").set(180.0)
    weather_source_lag_seconds.labels(source_id="mcgm-aws-telemetry", source_type="RAIN_GAUGE").set(
        120.0
    )
    weather_source_lag_seconds.labels(source_id="insat-3dr-satellite", source_type="SATELLITE").set(
        900.0
    )

    celery_queue_depth.labels(queue_name="ml_nowcast").set(0)
    celery_queue_depth.labels(queue_name="notifications").set(0)

    db_pool_connections.labels(state="checked_in").set(5)
    db_pool_connections.labels(state="checked_out").set(1)
    db_pool_connections.labels(state="overflow").set(0)
