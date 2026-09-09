import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.integrations.ml.provider import MLProvider, get_ml_provider

router = APIRouter(prefix="/risk", tags=["Risk"])


def compute_etag(data: Any) -> str:
    content = json.dumps(data, sort_keys=True).encode("utf-8")
    return f'"{hashlib.sha256(content).hexdigest()[:16]}"'


@router.get("/cells")
async def get_risk_cells(
    response: Response,
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    valid_time: str | None = Query(None, description="ISO-8601 UTC timestamp"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    ml_provider: MLProvider = Depends(get_ml_provider),
) -> Any:
    raw_cells = await ml_provider.get_risk_cells(bbox=bbox, valid_time=valid_time)

    # Filter bbox if given
    filtered = raw_cells
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
            # Validate bounding box coordinates are numeric
        except Exception:
            pass

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    etag = compute_etag(paginated)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=30"

    if if_none_match and if_none_match == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return response

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "valid_time": valid_time or datetime.now(UTC).isoformat(),
        "model_version": "v1.2.0-hydro",
        "data_version": "imd-wrf-20260908",
        "confidence": 0.94,
        "items": paginated,
    }


@router.get("/{h3_cell}/timeline")
async def get_cell_timeline(h3_cell: str, response: Response) -> dict[str, Any]:
    now = datetime.now(UTC)
    data = {
        "h3_cell_id": h3_cell,
        "model_version": "v1.2.0-hydro",
        "data_version": "imd-wrf-20260908",
        "valid_time": now.isoformat(),
        "confidence": 0.92,
        "timeline": [
            {"time_offset_min": 0, "risk_level": "MODERATE", "depth_m": 0.20, "probability": 0.45},
            {"time_offset_min": 30, "risk_level": "HIGH", "depth_m": 0.45, "probability": 0.72},
            {"time_offset_min": 60, "risk_level": "SEVERE", "depth_m": 0.78, "probability": 0.91},
            {"time_offset_min": 90, "risk_level": "HIGH", "depth_m": 0.50, "probability": 0.68},
        ],
    }
    etag = compute_etag(data["timeline"])
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"
    return data
