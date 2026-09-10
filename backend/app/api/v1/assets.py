import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/assets", tags=["Critical Assets"])


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
    assets = []
    if fixture_file.exists():
        with open(fixture_file, "r", encoding="utf-8") as f:
            assets = json.load(f)

    # Filter
    if asset_type:
        assets = [a for a in assets if a.get("asset_type") == asset_type]
    if status:
        assets = [a for a in assets if a.get("status") == status]

    total = len(assets)
    paginated = assets[offset : offset + limit]

    return {"total": total, "limit": limit, "offset": offset, "items": paginated}
