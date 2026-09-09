import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import NotFoundError, ValidationError
from app.domains.replay.manifest import HISTORICAL_REPLAY_MANIFEST


class ReplaySessionManager:
    """
    Manages deterministic historical replay sessions with a virtual clock.
    Guarantees that replay state and live operational data never mix.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, playback_speed: float = 1.0) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        timesteps = HISTORICAL_REPLAY_MANIFEST["timesteps"]
        session = {
            "session_id": session_id,
            "replay_id": HISTORICAL_REPLAY_MANIFEST["replay_id"],
            "event_title": HISTORICAL_REPLAY_MANIFEST["event_title"],
            "status": "PAUSED",
            "simulated_time": HISTORICAL_REPLAY_MANIFEST["start_time"],
            "start_time": HISTORICAL_REPLAY_MANIFEST["start_time"],
            "end_time": HISTORICAL_REPLAY_MANIFEST["end_time"],
            "playback_speed": max(0.25, min(playback_speed, 16.0)),
            "current_timestep_index": 0,
            "total_timesteps": len(timesteps),
            "is_replay_isolated": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            raise NotFoundError(f"Replay session '{session_id}' not found.")
        return self._sessions[session_id]

    def control_playback(
        self, session_id: str, action: str, speed: float | None = None
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        action_upper = action.upper()
        if action_upper not in ["PLAY", "PAUSE", "RESET", "STEP_FORWARD", "STEP_BACKWARD"]:
            raise ValidationError(
                f"Invalid control action '{action}'. Allowed: PLAY, PAUSE, RESET, STEP_FORWARD, STEP_BACKWARD"
            )

        timesteps = HISTORICAL_REPLAY_MANIFEST["timesteps"]
        curr_idx = session["current_timestep_index"]

        if action_upper == "PLAY":
            session["status"] = "PLAYING"
        elif action_upper == "PAUSE":
            session["status"] = "PAUSED"
        elif action_upper == "RESET":
            session["status"] = "PAUSED"
            session["simulated_time"] = session["start_time"]
            session["current_timestep_index"] = 0
        elif action_upper == "STEP_FORWARD":
            session["status"] = "PAUSED"
            new_idx = min(curr_idx + 1, len(timesteps) - 1)
            session["current_timestep_index"] = new_idx
            session["simulated_time"] = timesteps[new_idx]["timestamp"]
        elif action_upper == "STEP_BACKWARD":
            session["status"] = "PAUSED"
            new_idx = max(curr_idx - 1, 0)
            session["current_timestep_index"] = new_idx
            session["simulated_time"] = timesteps[new_idx]["timestamp"]

        if speed is not None and speed > 0:
            session["playback_speed"] = max(0.25, min(speed, 16.0))

        return session

    def scrub_to_timestamp(self, session_id: str, target_timestamp: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if target_timestamp < session["start_time"] or target_timestamp > session["end_time"]:
            raise ValidationError(
                f"Timestamp '{target_timestamp}' out of bounds. Valid range: [{session['start_time']} to {session['end_time']}]."
            )

        timesteps = HISTORICAL_REPLAY_MANIFEST["timesteps"]
        # Find closest timestep index
        closest_idx = 0
        for i, ts in enumerate(timesteps):
            if ts["timestamp"] <= target_timestamp:
                closest_idx = i

        session["simulated_time"] = target_timestamp
        session["current_timestep_index"] = closest_idx
        session["status"] = "PAUSED"
        return session

    def get_current_slice(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        timesteps = HISTORICAL_REPLAY_MANIFEST["timesteps"]
        idx = session["current_timestep_index"]
        slice_data = timesteps[idx]

        is_finished = (idx == len(timesteps) - 1) or (
            session["simulated_time"] >= session["end_time"]
        )

        return {
            "session": session,
            "temporal_slice": slice_data,
            "is_finished": is_finished,
            "predicted_vs_observed_metrics": HISTORICAL_REPLAY_MANIFEST[
                "predicted_vs_observed_metrics"
            ],
            "precomputed_tile_manifests": HISTORICAL_REPLAY_MANIFEST["precomputed_tile_manifests"],
        }


replay_manager = ReplaySessionManager()
