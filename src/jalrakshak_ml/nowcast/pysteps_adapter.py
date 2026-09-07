import logging
import warnings
from datetime import datetime

import numpy as np

from .contracts import NowcastResult, build_result

log = logging.getLogger(__name__)

class PystepsNowcast:
    """
    Adapter for pysteps optical flow nowcasting.
    Uses Lucas-Kanade for motion estimation and semi-Lagrangian extrapolation.
    """

    def __init__(self, fallback_to_persistence: bool = True):
        self.fallback = fallback_to_persistence
        
        # Lazy import to avoid hard crash if pysteps fails to load
        try:
            from pysteps.extrapolation.semilagrangian import extrapolate
            from pysteps.motion.lucaskanade import dense_lucaskanade
            self._dense_lucaskanade = dense_lucaskanade
            self._extrapolate = extrapolate
            self._is_available = True
        except ImportError:
            log.error("pysteps is not installed. PystepsNowcast will fail or fallback to persistence.")
            self._is_available = False

    def predict(self, recent_states: np.ndarray, lead_times: int) -> np.ndarray:
        """
        Generates an optical flow nowcast using pysteps.

        Args:
            recent_states (np.ndarray): 3D array of recent observations to compute motion.
                                        Shape: (time_steps, height, width).
                                        Requires at least 2 time steps (e.g., [t-1, t0]).
            lead_times (int): Number of future time steps to predict.

        Returns:
            np.ndarray: 3D array of predictions.
                        Shape: (lead_times, height, width).
        """
        if not self._is_available:
            if self.fallback:
                log.warning("pysteps unavailable. Falling back to persistence.")
                return self._persistence_fallback(recent_states, lead_times)
            else:
                raise ImportError("pysteps is required for PystepsNowcast.")

        if recent_states.ndim != 3 or recent_states.shape[0] < 2:
            log.warning("Pysteps requires at least 2 time steps (3D array). Falling back to persistence.")
            return self._persistence_fallback(recent_states, lead_times)

        if lead_times <= 0:
            raise ValueError("lead_times must be >= 1")

        log.info("Generating pysteps nowcast for %d lead times", lead_times)
        
        # Replace NaNs with 0 for motion estimation
        obs_clean = np.nan_to_num(recent_states, nan=0.0)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Compute motion field from the last two frames
            # Returns a dense motion field of shape (2, height, width)
            motion_field = self._dense_lucaskanade(obs_clean[-2:])
            
            # Extrapolate starting from the most recent frame
            forecast = self._extrapolate(obs_clean[-1], motion_field, lead_times)

        # Restore NaNs where the original latest frame had NaNs (optional, but good for masked regions)
        nan_mask = np.isnan(recent_states[-1])
        if np.any(nan_mask):
            forecast[:, nan_mask] = np.nan

        return forecast

    def _persistence_fallback(self, recent_states: np.ndarray, lead_times: int) -> np.ndarray:
        # If input is 3D, take the last frame
        latest = recent_states[-1] if recent_states.ndim == 3 else recent_states
        return np.broadcast_to(latest, (lead_times, *latest.shape)).copy()

    def predict_result(
        self,
        recent_states: np.ndarray,
        lead_times: int,
        *,
        issue_time: datetime,
        data_version: str,
        temporal_step_minutes: int = 30,
        source_metadata: dict | None = None,
    ) -> NowcastResult:
        return build_result(
            self.predict(recent_states, lead_times),
            issue_time=issue_time,
            provider="pysteps_lucaskanade",
            model_version="pysteps-lk-v1",
            data_version=data_version,
            temporal_step_minutes=temporal_step_minutes,
            source_metadata={
                **(source_metadata or {}),
                "pysteps_available": self._is_available,
                "fallback_to_persistence": not self._is_available and self.fallback,
            },
        )
