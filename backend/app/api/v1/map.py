"""Unified GIS and Map API endpoints with spatial bounding-box query support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.security import AuthenticatedUser, get_current_user
from app.domains.reports.repository import FieldReportsRepository
from app.integrations.ml.provider import get_ml_provider

router = APIRouter(prefix="/map", tags=["Map & Geospatial Queries"])

reports_repo = FieldReportsRepository(session=None)
ml_provider = get_ml_provider()


def _load_fixture_json(filename: str) -> Any:
    base = Path(__file__).resolve().parents[4]
    file_path = base / "contracts" / "fixtures" / "demo-event" / filename
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    return []


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
    except Exception:
        pass
    return None


@router.get("/risk", status_code=status.HTTP_200_OK)
async def get_map_risk_cells(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    min_level: str | None = Query(None, description="Minimum risk level: LOW, MODERATE, HIGH, SEVERE"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve risk cells with optional bounding box and minimum risk level filter."""
    cells = await ml_provider.get_risk_cells(bbox=bbox)
    level_weights = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "SEVERE": 4}
    threshold = level_weights.get(min_level.upper(), 1) if min_level else 1

    filtered = []
    for c in cells if isinstance(cells, list) else []:
        lvl = c.get("risk_level", "LOW")
        if level_weights.get(lvl, 1) >= threshold:
            filtered.append(c)

    # Return structured GIS payload
    return {
        "type": "RiskCellCollection",
        "bbox": bbox,
        "count": len(filtered),
        "features": filtered,
    }


@router.get("/incidents", status_code=status.HTTP_200_OK)
async def get_map_incidents(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    severity: str | None = Query(None, description="Filter by severity"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve incidents with spatial bbox and attribute filtering."""
    from app.api.v1.incidents import _memory_incidents

    fixture_incidents = _load_fixture_json("incidents.json")
    all_inc = list(_memory_incidents.values()) + (
        fixture_incidents if isinstance(fixture_incidents, list) else []
    )

    parsed_bbox = _parse_bbox(bbox)
    filtered = []
    for inc in all_inc:
        if severity and inc.get("severity") != severity.upper():
            continue
        if status_filter and inc.get("status") != status_filter.upper():
            continue
        lat = inc.get("latitude")
        lon = inc.get("longitude")
        if parsed_bbox and lat is not None and lon is not None:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
        filtered.append(inc)

    return {
        "type": "IncidentCollection",
        "bbox": bbox,
        "count": len(filtered),
        "features": filtered,
    }


@router.get("/reports", status_code=status.HTTP_200_OK)
async def get_map_reports(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    status_filter: str | None = Query(None, alias="status", description="Filter by verification status"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve citizen field reports with spatial bbox filtering."""
    reports = await reports_repo.list_reports(status=status_filter, bbox=bbox, limit=100)
    return {
        "type": "FieldReportCollection",
        "bbox": bbox,
        "count": len(reports),
        "features": reports,
    }


@router.get("/assets", status_code=status.HTTP_200_OK)
async def get_map_assets(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    category: str | None = Query(None, description="Filter by asset category"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve critical infrastructure assets with spatial bbox filtering."""
    fixture_assets = _load_fixture_json("critical-assets.json")
    parsed_bbox = _parse_bbox(bbox)

    filtered = []
    for asset in fixture_assets if isinstance(fixture_assets, list) else []:
        if category and asset.get("category", "").lower() != category.lower():
            continue
        lat = asset.get("latitude")
        lon = asset.get("longitude")
        if parsed_bbox and lat is not None and lon is not None:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
        filtered.append(asset)

    return {
        "type": "CriticalAssetCollection",
        "bbox": bbox,
        "count": len(filtered),
        "features": filtered,
    }


@router.get("/alerts", status_code=status.HTTP_200_OK)
async def get_map_alerts(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    severity: str | None = Query(None, description="Filter by alert severity"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve active emergency alerts formatted for map overlays."""
    from app.api.v1.alerts import _alerts_db

    fixture_alerts = _load_fixture_json("alerts.json")
    all_alerts = list(_alerts_db.values()) + (fixture_alerts if isinstance(fixture_alerts, list) else [])

    filtered = []
    for a in all_alerts:
        if a.get("status") not in ("APPROVED", "BROADCAST", "PUBLISHED"):
            continue
        if severity and a.get("severity", "").lower() != severity.lower():
            continue
        filtered.append(a)

    return {
        "type": "AlertCollection",
        "bbox": bbox,
        "count": len(filtered),
        "features": filtered,
    }
