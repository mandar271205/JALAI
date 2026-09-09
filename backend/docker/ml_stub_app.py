from fastapi import FastAPI
from datetime import datetime, timezone
import json

app = FastAPI(title="JalRakshak Internal ML Stub Service", version="1.0.0")

@app.get("/health")
def health():
    return {"status": "healthy", "service": "jalrakshak-ml-stub", "version": "1.0.0"}

@app.post("/internal/ml/nowcast")
def nowcast():
    return {
        "manifest_id": "stub-nowcast-latest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "valid_from": datetime.now(timezone.utc).isoformat(),
        "valid_to": datetime.now(timezone.utc).isoformat(),
        "lead_time_minutes": 120,
        "cog_url": "http://localhost:9000/jalrakshak/rasters/nowcast_latest.tif",
        "bounds": [72.75, 18.88, 73.02, 19.28],
        "model_version": "stub-precip-nowcast-v1",
        "data_version": "stub-radar-latest"
    }

@app.post("/internal/ml/inundation")
def inundation():
    return {
        "manifest_id": "stub-inundation-latest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "depth_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_depth_latest.tif",
        "velocity_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_velocity_latest.tif",
        "max_depth_meters": 1.45,
        "model_version": "stub-hydro-v1",
        "data_version": "stub-cwc-latest"
    }

@app.post("/internal/ml/risk-assessment")
def risk_assessment():
    return {
        "status": "success",
        "model_version": "stub-risk-aggregator-v1",
        "data_version": "stub-v1",
        "cells": [
            {
                "h3_cell_id": "8860145b53fffff",
                "valid_time": datetime.now(timezone.utc).isoformat(),
                "risk_level": "SEVERE",
                "confidence": 0.95,
                "flood_depth_m": 0.85,
                "rainfall_rate_mm_h": 68.5,
                "ward_id": "WARD-12-DHARAVI"
            }
        ]
    }

@app.post("/internal/ml/verify-report")
def verify_report(payload: dict):
    return {
        "report_id": payload.get("report_id", "stub-id"),
        "verification_status": "AI_VERIFIED",
        "confidence": 0.94,
        "detected_water_level_cm": 65.0,
        "is_flood_related": True,
        "model_version": "stub-report-vision-v1"
    }
