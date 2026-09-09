from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.security import AuthenticatedUser, get_current_user
from app.domains.replay.manifest import HISTORICAL_REPLAY_MANIFEST
from app.domains.replay.session import replay_manager

router = APIRouter(prefix="/replay", tags=["Historical Replay"])


@router.get("/manifest")
async def get_replay_manifest() -> dict[str, Any]:
    """
    Returns the immutable benchmark replay event manifest, containing timesteps,
    weather, risk cells, incidents, alerts, and precomputed tile manifests.
    """
    return HISTORICAL_REPLAY_MANIFEST


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_replay_session(
    payload: dict[str, Any] | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Spawns an isolated virtual-clock replay session.
    Live operational data and replay data are strictly segregated.
    """
    speed = float((payload or {}).get("playback_speed", 1.0))
    return replay_manager.create_session(playback_speed=speed)


@router.post("/sessions/{session_id}/control")
async def control_replay_playback(
    session_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Controls virtual replay playback: PLAY, PAUSE, RESET, STEP_FORWARD, STEP_BACKWARD.
    """
    action = payload.get("action", "PLAY")
    speed = payload.get("playback_speed")
    return replay_manager.control_playback(session_id=session_id, action=action, speed=speed)


@router.post("/sessions/{session_id}/scrub")
async def scrub_replay_time(
    session_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Scrubs virtual replay clock to an exact historical timestamp.
    """
    target_time = payload.get("timestamp")
    return replay_manager.scrub_to_timestamp(session_id=session_id, target_timestamp=target_time)


@router.get("/sessions/{session_id}/state")
async def get_replay_session_state(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns current temporal slice data (weather, model outputs, risk cells, incidents, alerts, tiles)
    for the specified virtual-clock replay session.
    """
    return replay_manager.get_current_slice(session_id)


@router.get("/metrics")
async def get_replay_model_accuracy_metrics() -> dict[str, Any]:
    """
    Exposes ML predicted-vs-observed evaluation metrics (RMSE, IoU, Brier Score, F1 score).
    """
    return HISTORICAL_REPLAY_MANIFEST["predicted_vs_observed_metrics"]
