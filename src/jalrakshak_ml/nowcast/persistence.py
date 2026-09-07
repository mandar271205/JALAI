import logging
from datetime import datetime

import numpy as np

from .contracts import NowcastResult, build_result

log = logging.getLogger(__name__)

class PersistenceNowcast:
    """
    Baseline nowcasting model that assumes the current state persists
    unchanged into the future for all lead times.
    """

    def __init__(self):
        pass

    def predict(self, current_state: np.ndarray, lead_times: int) -> np.ndarray:
        """
        Generates a persistence nowcast.

        Args:
            current_state (np.ndarray): 2D array of the current observation (e.g., rainfall rate).
                                        Shape: (height, width).
            lead_times (int): Number of future time steps to predict.

        Returns:
            np.ndarray: 3D array of predictions.
                        Shape: (lead_times, height, width).
        """
        if current_state.ndim != 2:
            raise ValueError(f"Expected 2D current_state, got {current_state.ndim}D")
        
        if lead_times <= 0:
            raise ValueError("lead_times must be >= 1")

        log.info("Generating persistence nowcast for %d lead times", lead_times)
        
        # Broadcast the current state along a new time dimension
        forecast = np.broadcast_to(current_state, (lead_times, *current_state.shape))
        
        # Make a copy so it's a writable, independent array
        return forecast.copy()

    def predict_result(
        self,
        current_state: np.ndarray,
        lead_times: int,
        *,
        issue_time: datetime,
        data_version: str,
        temporal_step_minutes: int = 30,
        source_metadata: dict | None = None,
    ) -> NowcastResult:
        return build_result(
            self.predict(current_state, lead_times),
            issue_time=issue_time,
            provider="persistence",
            model_version="persistence-v1",
            data_version=data_version,
            temporal_step_minutes=temporal_step_minutes,
            source_metadata=source_metadata,
        )
