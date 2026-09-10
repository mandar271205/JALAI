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


H3_CENTROIDS: dict[str, tuple[float, float]] = {
    "8860145b53fffff": (19.0432, 72.8550),  # Dharavi
    "8860145b51fffff": (19.0712, 72.8756),  # Kurla
    "8860145b57fffff": (19.0178, 72.8478),  # Dadar
    "8860145a33fffff": (19.1197, 72.8397),  # Andheri
}


@router.get("/risk", status_code=status.HTTP_200_OK)
async def get_map_risk_cells(
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    min_level: str | None = Query(None, description="Minimum risk level: LOW, MODERATE, HIGH, SEVERE"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve risk cells with optional bounding box and minimum risk level filter."""
    from app.api.v1.simulation import get_active_simulation

    cells = await ml_provider.get_risk_cells(bbox=bbox)
    level_weights = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "SEVERE": 4}
    threshold = level_weights.get(min_level.upper(), 1) if min_level else 1
    parsed_bbox = _parse_bbox(bbox)

    all_cells = list(cells) if isinstance(cells, list) else []

    sim = get_active_simulation()
    if sim.get("is_active") and sim.get("h3_cell_id"):
        sim_cell = {
            "h3_cell_id": sim["h3_cell_id"],
            "ward_id": sim["ward_id"],
            "ward_name": sim["ward_name"],
            "risk_level": sim["risk_level"],
            "confidence": 0.96,
            "rainfall_rate_mm_h": sim["rainfall_rate_mm_h"],
            "latitude": sim["latitude"],
            "longitude": sim["longitude"],
            "is_simulated": True,
            "scenario_name": sim["scenario_name"],
        }
        # Replace if cell exists or prepend
        all_cells = [c for c in all_cells if c.get("h3_cell_id") != sim["h3_cell_id"]]
        all_cells.insert(0, sim_cell)

    filtered = []
    for c in all_cells:
        c_copy = dict(c)
        cell_id = c_copy.get("h3_cell_id")
        coords = H3_CENTROIDS.get(cell_id, (19.0760, 72.8777))
        lat = c_copy.get("latitude") or coords[0]
        lon = c_copy.get("longitude") or coords[1]
        c_copy["latitude"] = lat
        c_copy["longitude"] = lon

        if parsed_bbox:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue

        lvl = c_copy.get("risk_level", "LOW")
        if level_weights.get(lvl, 1) >= threshold:
            filtered.append(c_copy)

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
        loc = inc.get("location") or {}
        lat = inc.get("latitude") or loc.get("latitude")
        lon = inc.get("longitude") or loc.get("longitude")
        if parsed_bbox and lat is not None and lon is not None:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
        inc_copy = dict(inc)
        if lat is not None:
            inc_copy["latitude"] = lat
        if lon is not None:
            inc_copy["longitude"] = lon
        filtered.append(inc_copy)

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
    all_reports = list(reports)
    if not all_reports:
        fixture_reports = _load_fixture_json("reports.json")
        if isinstance(fixture_reports, list):
            all_reports.extend(fixture_reports)

    parsed_bbox = _parse_bbox(bbox)
    filtered = []
    for rep in all_reports:
        loc = rep.get("location") or {}
        lat = rep.get("latitude") or loc.get("latitude")
        lon = rep.get("longitude") or loc.get("longitude")
        if parsed_bbox and lat is not None and lon is not None:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
        rep_copy = dict(rep)
        if lat is not None:
            rep_copy["latitude"] = lat
        if lon is not None:
            rep_copy["longitude"] = lon
        filtered.append(rep_copy)

    return {
        "type": "FieldReportCollection",
        "bbox": bbox,
        "count": len(filtered),
        "features": filtered,
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
        loc = asset.get("location") or {}
        lat = asset.get("latitude") or loc.get("latitude")
        lon = asset.get("longitude") or loc.get("longitude")
        if parsed_bbox and lat is not None and lon is not None:
            min_lon, min_lat, max_lon, max_lat = parsed_bbox
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                continue
        asset_copy = dict(asset)
        if lat is not None:
            asset_copy["latitude"] = lat
        if lon is not None:
            asset_copy["longitude"] = lon
        filtered.append(asset_copy)

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
