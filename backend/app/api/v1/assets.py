import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/assets", tags=["Critical Assets"])

_custom_assets: list[dict[str, Any]] = []


@router.get("")
async def list_critical_assets(
    asset_type: str | None = Query(
        None, description="HOSPITAL, POWER_SUBSTATION, FIRE_STATION, RELIEF_SHELTER"
    ),
    status: str | None = Query(None, description="NORMAL, AT_RISK, INUNDATED, OFFLINE"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    base = Path(__file__).resolve().parents[3]
    fixture_file = base / "contracts" / "fixtures" / "demo-event" / "critical-assets.json"
    if not fixture_file.exists():
        fixture_file = Path(__file__).resolve().parents[4] / "contracts" / "fixtures" / "demo-event" / "critical-assets.json"
    assets = list(_custom_assets)
    if fixture_file.exists():
        with open(fixture_file, "r", encoding="utf-8") as f:
            assets.extend(json.load(f))

    # Filter
    if asset_type:
        assets = [a for a in assets if a.get("asset_type") == asset_type]
    if status:
        assets = [a for a in assets if a.get("status") == status]

    total = len(assets)
    paginated = assets[offset : offset + limit]

    return {"total": total, "limit": limit, "offset": offset, "items": paginated}


@router.post("", status_code=201)
async def create_critical_asset(payload: dict[str, Any]) -> dict[str, Any]:
    """Register a new critical infrastructure asset."""
    import uuid

    asset_id = payload.get("asset_id") or f"asset-{uuid.uuid4().hex[:8]}"
    asset = {
        "asset_id": asset_id,
        "name": payload.get("name", "Critical Facility"),
        "asset_type": payload.get("asset_type", "PUMPING_STATION"),
        "ward_id": payload.get("ward_id", "G-North"),
        "latitude": float(payload.get("latitude", 19.0330)),
        "longitude": float(payload.get("longitude", 72.8570)),
        "status": payload.get("status", "AT_RISK"),
        "risk_level": payload.get("risk_level", "SEVERE"),
        "inundation_threshold_m": float(payload.get("inundation_threshold_m", 0.45)),
    }
    _custom_assets.insert(0, asset)
    return asset
