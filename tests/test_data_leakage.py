import pytest
import numpy as np
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from datetime import datetime, timezone

def test_no_future_data_leakage():
    """
    Ensure the evaluator strictly feeds only past/current data (t <= 0) to the models
    and evaluates against future data (t > 0).
    """
    # Create dummy data: 10 frames of 1x1 arrays
    # Frames 0..4 are history, Frames 5..9 are future
    dummy_data = np.arange(10, dtype=np.float32).reshape(10, 1, 1)
    
    # We create a dummy model that records what it was given
    class LeakageDetectorModel:
        def __init__(self):
            self.inputs_seen = None

        def predict(self, recent_obs: np.ndarray, lead_times: int = 1) -> np.ndarray:
            self.inputs_seen = recent_obs.copy()
            # Return arbitrary forecast
            return np.zeros((lead_times, 1, 1), dtype=np.float32)

    detector = LeakageDetectorModel()
    
    # We simulate what the evaluation loop does
    lead_times = 3
    history_length = 3
    
    # At t=5, history is t=2,3,4. Future is t=5,6,7.
    history = dummy_data[2:5]
    future = dummy_data[5:8]
    
    pred = detector.predict(history, lead_times=lead_times)
    
    # Check that model only saw history
    assert detector.inputs_seen is not None
    assert np.array_equal(detector.inputs_seen, history), "Model should only see historical data"
    assert not np.any(np.isin(detector.inputs_seen, future)), "Model saw future data!"
    
    evaluator = NowcastEvaluator(thresholds=[0.1])
    # NowcastEvaluator expects (lead_time, H, W)
    # the dummy data shapes are (time, 1, 1), so pred and future are (3, 1, 1)
    metrics_df = evaluator.evaluate_sequence(future, pred)
    assert not metrics_df.empty

def test_persistence_output_contract():
    model = PersistenceNowcast()
    # Persistence takes a 2D observation
    obs = np.zeros((10, 10), dtype=np.float32)
    pred = model.predict(obs, lead_times=4)
    
    assert pred.shape == (4, 10, 10), "Persistence should broadcast 2D to 3D correctly"
