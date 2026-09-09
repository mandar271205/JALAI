from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.live import router as live_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.metrics import (
    PrometheusMetricsMiddleware,
    get_prometheus_metrics,
    record_initial_gauges,
)
from app.core.security_hardening import (
    PayloadSizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.sentry import init_sentry
from app.core.telemetry import TraceIdMiddleware, setup_logging
from app.db.session import engine
from app.integrations.object_store.provider import get_object_store_provider

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.LOG_LEVEL)
    # Initialize Sentry if configured
    init_sentry(settings.SENTRY_DSN, settings.APP_ENV)
    # Seed Prometheus operational gauges
    record_initial_gauges()
    # Ensure object storage bucket exists
    try:
        store = get_object_store_provider()
        await store.ensure_bucket()
    except Exception:
        pass
    yield
    # Cleanup DB engine connections
    await engine.dispose()


app = FastAPI(
    title="JalRakshak AI - Backend API",
    description="Backend Platform API for Disaster Management, Flood Risk Nowcasting, and Field Operations (SIH26071).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middlewares
app.add_middleware(TraceIdMiddleware)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# Observability & Metrics
@app.get("/metrics", tags=["Observability"])
async def prometheus_metrics_endpoint() -> Response:
    """Exposes operational Prometheus metrics for Grafana scraping."""
    payload, content_type = get_prometheus_metrics()
    return Response(content=payload, media_type=content_type)


# Health & Readiness Probes
@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Liveness probe returning 200 if the process is responsive."""
    return {"status": "ok", "service": "jalrakshak-backend", "version": "1.0.0"}


@app.get("/ready", tags=["Health"])
async def readiness_check() -> dict[str, Any]:
    """Readiness probe checking database, redis and storage dependencies."""
    checks = {"database": "unknown", "redis": "unknown", "object_store": "unknown"}

    # 1. DB check
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)[:50]}"

    # 2. Redis check
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)[:50]}"

    # 3. Object Store check
    try:
        store = get_object_store_provider()
        ok = await store.ensure_bucket()
        checks["object_store"] = "healthy" if ok else "degraded"
    except Exception as e:
        checks["object_store"] = f"unhealthy: {str(e)[:50]}"

    is_ready = checks["database"] == "healthy" or settings.APP_ENV in ["local", "test"]
    return {"ready": is_ready, "environment": settings.APP_ENV, "dependencies": checks}


# Mount Public API v1
app.include_router(api_v1_router)
app.include_router(live_router)
