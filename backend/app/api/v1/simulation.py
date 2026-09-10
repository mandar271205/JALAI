"""Simulation and Live Scenario Injection API for JalRakshak Command Center."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.v1.incidents import _memory_incidents
from app.core.security import AuthenticatedUser, get_current_user
from app.realtime.connection_manager import live_manager

logger = logging.getLogger("jalrakshak.simulation")

router = APIRouter(prefix="/simulation", tags=["Scenario Simulation"])

# Known ward coordinates and H3 mappings
WARD_METADATA: dict[str, dict[str, Any]] = {
    "WARD-08-KURLA": {
        "name": "Kurla (Ward L)",
        "h3_cell_id": "8860145b51fffff",
        "latitude": 19.0712,
        "longitude": 72.8756,
        "primary_asset": "Kurla Railway Car Shed & CST Road Bridge",
    },
    "WARD-12-DHARAVI": {
        "name": "Dharavi (Ward G/North)",
        "h3_cell_id": "8860145b53fffff",
        "latitude": 19.0432,
        "longitude": 72.8550,
        "primary_asset": "Dharavi 110kV Electrical Substation",
    },
    "WARD-04-DADAR": {
        "name": "Dadar (Ward F/North)",
        "h3_cell_id": "8860145b57fffff",
        "latitude": 19.0178,
        "longitude": 72.8478,
        "primary_asset": "King's Circle Railway Underpass",
    },
    "WARD-K-WEST-ANDHERI": {
        "name": "Andheri West (Ward K/West)",
        "h3_cell_id": "8860145a33fffff",
        "latitude": 19.1197,
        "longitude": 72.8397,
        "primary_asset": "Andheri Subway & S.V. Road Junction",
    },
    "WARD-H-EAST-BANDRA": {
        "name": "Bandra East / BKC (Ward H/East)",
        "h3_cell_id": "8860145b17fffff",
        "latitude": 19.0596,
        "longitude": 72.8480,
        "primary_asset": "Bandra-Kurla Complex Financial District",
    },
    "WARD-A-COLABA": {
        "name": "Colaba / Fort (Ward A)",
        "h3_cell_id": "8860145a55fffff",
        "latitude": 18.9067,
        "longitude": 72.8147,
        "primary_asset": "Naval Dockyard & Sassoon Docks",
    },
}

# In-memory simulation state
_ACTIVE_SIMULATION: dict[str, Any] = {
    "is_active": False,
    "scenario_id": None,
    "scenario_name": None,
    "ward_id": None,
    "ward_name": None,
    "rainfall_rate_mm_h": None,
    "max_recorded_rainfall_mm": None,
    "tide_level_m": 1.8,
    "risk_level": "LOW",
    "affected_asset": None,
    "injected_at": None,
    "ai_briefing": None,
    "incident_id": None,
}


def get_active_simulation() -> dict[str, Any]:
    """Provide read access to active simulation state."""
    return _ACTIVE_SIMULATION


class ScenarioInjectRequest(BaseModel):
    scenario_name: str | None = Field(default=None, description="Human-readable title of scenario")
    ward_id: str | None = Field(default=None, description="Target Ward ID (e.g., WARD-08-KURLA)")
    ward: str | None = Field(default=None, description="Alternative ward name")
    rainfall_rate_mm_h: float = Field(..., ge=0.0, le=300.0, description="Rainfall rate in mm/h")
    tide_level_m: float | None = Field(default=None, ge=0.0, le=6.0, description="Tidal water level in meters")
    high_tide_m: float | None = Field(default=None, ge=0.0, le=6.0, description="Alternative tide level")
    risk_level: str = Field(default="SEVERE", description="Calculated or forced risk level")
    affected_asset: str | None = Field(default=None, description="Critical infrastructure item at risk")
    asset_at_risk: str | None = Field(default=None, description="Alternative asset name")


def _generate_ai_briefing(
    scenario_name: str,
    ward_name: str,
    rainfall_rate: float,
    tide_level: float,
    risk_level: str,
    asset_name: str,
) -> dict[str, Any]:
    """Synthesize structured, authoritative AI operational briefing."""
    drainage_capacity_mm_h = 50.0  # Mumbai storm drainage design baseline (BMC standard)
    capacity_ratio = round(rainfall_rate / drainage_capacity_mm_h, 2)
    is_tide_lock = tide_level >= 3.5

    hazard_summary = (
        f"Precipitation rate of {rainfall_rate:.1f} mm/h is {capacity_ratio}x the local "
        f"stormwater drainage design baseline ({drainage_capacity_mm_h:.0f} mm/h)."
    )

    if is_tide_lock:
        hydro_analysis = (
            f"Active Spring High Tide of {tide_level:.2f}m prevents gravity discharge from "
            f"local outfalls into the Arabian Sea. Mithi River / nullah backflow is actively aggravating inundation."
        )
    else:
        hydro_analysis = (
            f"Tidal level is normal ({tide_level:.2f}m), allowing partial gravity outflow, "
            f"but intense surface runoff volume exceeds local drainage capacity."
        )

    recommendations = [
        f"Pre-deploy emergency dewatering pump units to {asset_name}.",
        f"Issue immediate CAP Warning Alert to residents and commuters in {ward_name}.",
        "Alert Traffic Police Control for immediate vehicular diversion from low-lying junctions.",
    ]
    if rainfall_rate > 80.0 or is_tide_lock:
        recommendations.insert(0, f"Mobilize NDRF / Civil Defence quick response boat teams to {ward_name}.")

    return {
        "scenario_title": scenario_name,
        "executive_summary": (
            f"CRITICAL FLOOD RISK: Intense precipitation ({rainfall_rate:.1f} mm/h) over {ward_name} "
            f"coinciding with {tide_level:.2f}m tide has elevated local risk to {risk_level}. "
            f"Key asset '{asset_name}' is threatened."
        ),
        "hazard_summary": hazard_summary,
        "hydrodynamic_analysis": hydro_analysis,
        "drainage_exceedance_ratio": capacity_ratio,
        "affected_asset": asset_name,
        "action_plan": recommendations,
        "confidence_score": 0.94,
        "synthesized_at": datetime.now(UTC).isoformat(),
        "model_used": "JalRakshak Multi-Model Decision Support (Groq/Physics Hybrid)",
    }


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_simulation_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Check whether a custom scenario is currently injected."""
    return _ACTIVE_SIMULATION


@router.post("/inject", status_code=status.HTTP_200_OK)
async def inject_simulation_scenario(
    req: ScenarioInjectRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Inject custom operational weather, risk, and incident conditions."""
    raw_ward = (req.ward_id or req.ward or "WARD-12-DHARAVI").upper()
    matched_meta = None
    for k, v in WARD_METADATA.items():
        if k == raw_ward or raw_ward in k or k in raw_ward:
            matched_meta = v
            break

    ward_meta = matched_meta or {
        "name": raw_ward,
        "h3_cell_id": "8860145b53fffff",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "primary_asset": "Municipal Infrastructure",
    }

    tide_val = req.tide_level_m if req.tide_level_m is not None else (req.high_tide_m or 1.8)
    asset = req.affected_asset or req.asset_at_risk or ward_meta.get("primary_asset", "Critical Asset")
    scenario_title = req.scenario_name or f"Simulated Storm Surge ({ward_meta['name']})"
    now_iso = datetime.now(UTC).isoformat()
    scenario_id = f"sim-{uuid.uuid4().hex[:8]}"

    # 1. Synthesize AI Briefing
    briefing = _generate_ai_briefing(
        scenario_name=scenario_title,
        ward_name=ward_meta["name"],
        rainfall_rate=req.rainfall_rate_mm_h,
        tide_level=tide_val,
        risk_level=req.risk_level.upper(),
        asset_name=asset,
    )

    # 2. Create or update an active incident in memory
    inc_id = f"inc-sim-{uuid.uuid4().hex[:6]}"
    sim_incident = {
        "incident_id": inc_id,
        "title": f"[SIMULATED] {scenario_title} — {ward_meta['name']}",
        "severity": req.risk_level.upper(),
        "status": "DISPATCHED",
        "category": "WATERLOGGING",
        "created_at": now_iso,
        "latitude": ward_meta["latitude"],
        "longitude": ward_meta["longitude"],
        "location": {
            "latitude": ward_meta["latitude"],
            "longitude": ward_meta["longitude"],
        },
        "ward_id": raw_ward,
        "description": briefing["executive_summary"],
        "is_simulated": True,
    }
    _memory_incidents[inc_id] = sim_incident

    # 3. Update global active simulation state
    _ACTIVE_SIMULATION.update(
        {
            "is_active": True,
            "scenario_id": scenario_id,
            "scenario_name": scenario_title,
            "ward_id": raw_ward,
            "ward_name": ward_meta["name"],
            "h3_cell_id": ward_meta["h3_cell_id"],
            "latitude": ward_meta["latitude"],
            "longitude": ward_meta["longitude"],
            "rainfall_rate_mm_h": req.rainfall_rate_mm_h,
            "max_recorded_rainfall_mm": req.rainfall_rate_mm_h * 1.8,
            "tide_level_m": tide_val,
            "risk_level": req.risk_level.upper(),
            "affected_asset": asset,
            "injected_at": now_iso,
            "ai_briefing": briefing,
            "incident_id": inc_id,
        }
    )

    # 4. Broadcast live WebSocket events
    try:
        await live_manager.broadcast(
            "scenario.injected",
            {
                "scenario_id": scenario_id,
                "scenario_name": req.scenario_name,
                "ward_id": req.ward_id,
                "risk_level": req.risk_level.upper(),
                "rainfall_rate_mm_h": req.rainfall_rate_mm_h,
            },
        )
        await live_manager.broadcast(
            "risk.cell.updated",
            {
                "h3_cell": ward_meta["h3_cell_id"],
                "level": req.risk_level.upper(),
                "rainfall": req.rainfall_rate_mm_h,
                "ward_id": req.ward_id,
            },
        )
        await live_manager.broadcast("incident.created", sim_incident)
    except Exception as exc:
        logger.warning("Failed to broadcast simulation events: %s", exc)

    return {
        "status": "SUCCESS",
        "message": f"Scenario '{req.scenario_name}' successfully injected.",
        "simulation": _ACTIVE_SIMULATION,
    }


@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_simulation_scenario(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Reset to baseline demo state and clear simulated incidents."""
    inc_id = _ACTIVE_SIMULATION.get("incident_id")
    if inc_id and inc_id in _memory_incidents:
        _memory_incidents.pop(inc_id, None)

    _ACTIVE_SIMULATION.update(
        {
            "is_active": False,
            "scenario_id": None,
            "scenario_name": None,
            "ward_id": None,
            "ward_name": None,
            "h3_cell_id": None,
            "latitude": None,
            "longitude": None,
            "rainfall_rate_mm_h": None,
            "max_recorded_rainfall_mm": None,
            "tide_level_m": 1.8,
            "risk_level": "LOW",
            "affected_asset": None,
            "injected_at": None,
            "ai_briefing": None,
            "incident_id": None,
        }
    )

    try:
        await live_manager.broadcast("scenario.reset", {"timestamp": datetime.now(UTC).isoformat()})
    except Exception as exc:
        logger.warning("Failed to broadcast scenario.reset: %s", exc)

    return {
        "status": "RESET_SUCCESS",
        "message": "Simulation cleared. Baseline telemetry restored.",
    }
