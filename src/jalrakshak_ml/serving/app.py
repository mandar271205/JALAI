"""FastAPI application for the JalRakshak ML Serving Service (SIH26071).

Exposes:
- Canonical versioned contracts: /internal/v1/...
- Teammate backward-compatibility aliases: /internal/ml/...
- Health checks: /health
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware

from jalrakshak_ml.serving.schemas import (
    InundationManifestResponse,
    InundationRequest,
    ModelsStatusResponse,
    NowcastManifestResponse,
    NowcastRequest,
    ReportVerificationRequest,
    ReportVerificationResponse,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
)
from jalrakshak_ml.serving.service import ml_service

logger = logging.getLogger("jalrakshak.ml.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

AUTH_TOKEN = os.getenv("ML_SERVICE_TOKEN", "dev-ml-token")


def verify_token(authorization: str | None = Header(None)) -> str:
    """Validate internal service-to-service Bearer token."""
    # Allow test/dev mode without token if explicitly disabled, or validate Bearer
    if not AUTH_TOKEN or AUTH_TOKEN == "none":
        return "unauthenticated-dev"

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token.strip() != AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal ML service token",
        )
    return token


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("JalRakshak ML Inference Service starting up on port 8001.")
    yield
    logger.info("JalRakshak ML Inference Service shut down.")


app = FastAPI(
    title="JalRakshak ML Inference Service",
    description="Internal ML inference microservice for Rainfall Nowcasting, Flood Susceptibility, and H3 Risk Engine (SIH26071).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health & Readiness ---

@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "jalrakshak-ml-service", "version": "1.0.0"}


# --- Canonical /internal/v1 Routes ---

@app.post(
    "/internal/v1/nowcast",
    response_model=NowcastManifestResponse,
    tags=["Canonical Nowcast"],
    dependencies=[Depends(verify_token)],
)
async def run_nowcast_v1(req: NowcastRequest | None = None) -> NowcastManifestResponse:
    request_data = req or NowcastRequest()
    return ml_service.run_nowcast(request_data)


@app.post(
    "/internal/v1/inundation",
    response_model=InundationManifestResponse,
    tags=["Canonical Inundation"],
    dependencies=[Depends(verify_token)],
)
async def run_inundation_v1(req: InundationRequest | None = None) -> InundationManifestResponse:
    request_data = req or InundationRequest()
    return ml_service.run_inundation(request_data)


@app.post(
    "/internal/v1/risk",
    response_model=RiskAssessmentResponse,
    tags=["Canonical Risk"],
    dependencies=[Depends(verify_token)],
)
async def run_risk_v1(req: RiskAssessmentRequest | None = None) -> RiskAssessmentResponse:
    request_data = req or RiskAssessmentRequest()
    return ml_service.run_risk_assessment(request_data)


@app.post(
    "/internal/v1/report-verification",
    response_model=ReportVerificationResponse,
    tags=["Canonical Reports"],
    dependencies=[Depends(verify_token)],
)
async def verify_report_v1(req: ReportVerificationRequest) -> ReportVerificationResponse:
    return ml_service.verify_citizen_report(req)


@app.get(
    "/internal/v1/models/status",
    response_model=ModelsStatusResponse,
    tags=["Canonical Models"],
    dependencies=[Depends(verify_token)],
)
async def get_models_status_v1() -> ModelsStatusResponse:
    return ml_service.get_models_status()


@app.get(
    "/internal/v1/runs/{run_id}",
    tags=["Canonical Runs"],
    dependencies=[Depends(verify_token)],
)
async def get_run_v1(run_id: str) -> dict[str, Any]:
    run = ml_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")
    return run


# --- Teammate Backward-Compatibility Aliases (/internal/ml/...) ---

@app.post(
    "/internal/ml/nowcast",
    response_model=NowcastManifestResponse,
    tags=["Backend Compatibility Aliases"],
    dependencies=[Depends(verify_token)],
)
async def run_nowcast_alias(payload: dict[str, Any] | None = None) -> NowcastManifestResponse:
    req = NowcastRequest.model_validate(payload or {})
    return ml_service.run_nowcast(req)


@app.post(
    "/internal/ml/inundation",
    response_model=InundationManifestResponse,
    tags=["Backend Compatibility Aliases"],
    dependencies=[Depends(verify_token)],
)
async def run_inundation_alias(payload: dict[str, Any] | None = None) -> InundationManifestResponse:
    req = InundationRequest.model_validate(payload or {})
    return ml_service.run_inundation(req)


@app.post(
    "/internal/ml/risk-assessment",
    tags=["Backend Compatibility Aliases"],
    dependencies=[Depends(verify_token)],
)
async def run_risk_alias(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    req = RiskAssessmentRequest.model_validate(payload or {})
    result = ml_service.run_risk_assessment(req)
    # Return both envelope and direct "cells" key for backend HttpMLProvider compatibility
    return result.model_dump()


@app.post(
    "/internal/ml/verify-report",
    response_model=ReportVerificationResponse,
    tags=["Backend Compatibility Aliases"],
    dependencies=[Depends(verify_token)],
)
async def verify_report_alias(payload: dict[str, Any]) -> ReportVerificationResponse:
    req = ReportVerificationRequest.model_validate(payload)
    return ml_service.verify_citizen_report(req)
