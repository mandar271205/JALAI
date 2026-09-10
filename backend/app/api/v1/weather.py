import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Response, status

router = APIRouter(prefix="/weather", tags=["Weather"])


def compute_etag(data: Any) -> str:
    content = json.dumps(data, sort_keys=True).encode("utf-8")
    return f'"{hashlib.sha256(content).hexdigest()[:16]}"'


@router.get("/current")
async def get_current_weather(
    response: Response, if_none_match: str | None = Header(None, alias="If-None-Match")
) -> Any:
    from app.api.v1.simulation import get_active_simulation

    sim = get_active_simulation()
    if sim.get("is_active"):
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": f"[SIMULATED] {sim.get('scenario_name')} — {sim.get('ward_name')}",
            "average_rainfall_rate_mm_h": sim.get("rainfall_rate_mm_h", 48.5),
            "max_recorded_rainfall_mm": sim.get("max_recorded_rainfall_mm", 112.0),
            "active_stations": 42,
            "model_version": "imd-wrf-highres-v4 (Simulated Scenario)",
            "data_version": "mumbai-telemetry-live",
            "confidence": 0.96,
            "is_simulated": True,
            "simulated_scenario_id": sim.get("scenario_id"),
        }
    else:
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "summary": "Heavy monsoon rainfall over Mumbai metropolitan region",
            "average_rainfall_rate_mm_h": 48.5,
            "max_recorded_rainfall_mm": 112.0,
            "active_stations": 42,
            "model_version": "imd-wrf-highres-v4",
            "data_version": "mumbai-telemetry-live",
            "confidence": 0.95,
            "is_simulated": False,
        }
    # Deterministic etag using fixed keys
    etag = compute_etag({k: v for k, v in data.items() if k != "timestamp"})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache" if sim.get("is_active") else "public, max-age=60"

    if if_none_match and if_none_match == etag and not sim.get("is_active"):
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return response

    return data


@router.get("/sources/status")
async def get_weather_sources_status(
    response: Response, if_none_match: str | None = Header(None, alias="If-None-Match")
) -> Any:
    base = Path(__file__).resolve().parents[4]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "weather-sources.json"
    sources = []
    if fixture_file.exists():
        with open(fixture_file) as f:
            sources = json.load(f)
    else:
        sources = [
            {
                "source_id": "imd-radar-mumbai",
                "name": "IMD Doppler Weather Radar (Mumbai/Colaba)",
                "source_type": "RADAR",
                "status": "HEALTHY",
                "last_successful_ingestion": datetime.now(UTC).isoformat(),
                "latency_seconds": 180.0,
            }
        ]

    etag = compute_etag(sources)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"

    if if_none_match and if_none_match == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return response

    return sources
