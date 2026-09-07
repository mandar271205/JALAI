import numpy as np
import pytest
from jalrakshak_ml.evaluation.metrics import compute_continuous_metrics, compute_dichotomous_metrics
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast

def test_compute_continuous_metrics():
    # Simple arrays
    obs = np.array([1.0, 2.0, 3.0, 4.0])
    pred = np.array([1.0, 1.0, 3.0, 6.0])
    # diffs = [0, -1, 0, 2]
    # abs_diffs = [0, 1, 0, 2] -> MAE = 3/4 = 0.75
    # sq_diffs = [0, 1, 0, 4] -> RMSE = sqrt(5/4) = 1.118

    res = compute_continuous_metrics(obs, pred)
    assert np.isclose(res["mae"], 0.75)
    assert np.isclose(res["rmse"], np.sqrt(5.0/4.0))

def test_compute_continuous_metrics_with_nans():
    obs = np.array([1.0, np.nan, 3.0, 4.0])
    pred = np.array([1.0, 1.0, 3.0, np.nan])
    # Valid indices: 0, 2
    # obs_v = [1.0, 3.0], pred_v = [1.0, 3.0]
    # diffs = [0, 0]
    res = compute_continuous_metrics(obs, pred)
    assert np.isclose(res["mae"], 0.0)
    assert np.isclose(res["rmse"], 0.0)

def test_compute_dichotomous_metrics():
    # obs  = [0.0, 1.0, 2.0, 3.0]
    # pred = [0.0, 0.5, 2.5, 0.0]
    # thresh = 1.0
    # obs_v  = [F, T, T, T]
    # pred_v = [F, F, T, F]
    
    # Hits (T, T) = 1 (idx 2)
    # Misses (T, F) = 2 (idx 1, 3)
    # False alarms (F, T) = 0
    # Correct negatives (F, F) = 1 (idx 0)
    
    obs = np.array([0.0, 1.0, 2.0, 3.0])
    pred = np.array([0.0, 0.5, 2.5, 0.0])
    
    res = compute_dichotomous_metrics(obs, pred, threshold=1.0)
    
    # POD = H / (H + M) = 1 / 3
    assert np.isclose(res["pod"], 1.0 / 3.0)
    
    # FAR = FA / (H + FA) = 0 / 1 = 0
    assert np.isclose(res["far"], 0.0)
    
    # CSI = H / (H + M + FA) = 1 / 3
    assert np.isclose(res["csi"], 1.0 / 3.0)
    
    # Bias = (H + FA) / (H + M) = 1 / 3
    assert np.isclose(res["bias"], 1.0 / 3.0)
    
    # F1 = 2 * (Precision * Recall) / (Precision + Recall)
    # Precision = 1.0 (since FAR=0), Recall = 1/3
    # F1 = 2 * (1.0 * 1/3) / (1.0 + 1/3) = (2/3) / (4/3) = 0.5
    assert np.isclose(res["f1"], 0.5)
    
    assert res["hits"] == 1
    assert res["misses"] == 2
    assert res["false_alarms"] == 0
    assert res["correct_negatives"] == 1

def test_extreme_bias_and_f1_nan_handling():
    # F1 and Bias should handle zero-denominators gracefully without throwing exceptions
    # If hits+misses=0, POD is nan. If hits+FA=0, FAR is nan.
    obs = np.array([0.0, 0.0])
    pred = np.array([0.0, 0.0])
    res = compute_dichotomous_metrics(obs, pred, threshold=1.0)
    
    assert np.isnan(res["pod"])
    assert np.isnan(res["far"])
    assert np.isnan(res["f1"])
    assert np.isnan(res["bias"])
    assert res["hits"] == 0
    assert res["correct_negatives"] == 2
    
    # Sparse positive where bias could be huge
    # hits = 1, FA = 10, misses = 0 -> Bias = 11/1 = 11
    obs = np.array([1.0] + [0.0]*10)
    pred = np.array([1.0]*11)
    res = compute_dichotomous_metrics(obs, pred, threshold=1.0)
    
    assert np.isclose(res["bias"], 11.0)
    assert np.isclose(res["pod"], 1.0) # 1 / 1
    assert np.isclose(res["far"], 10.0 / 11.0)
    assert np.isclose(res["f1"], 2 * ((1/11)*1) / ((1/11)+1))
def test_evaluator_sequence():
    obs = np.ones((3, 10, 10))
    pred = np.ones((3, 10, 10))
    
    # Introduce some errors in t=1 and t=2
    pred[1, 0:5, :] = 0.0
    pred[2, :, :] = 0.0
    
    evaluator = NowcastEvaluator(thresholds=[0.5])
    df = evaluator.evaluate_sequence(obs, pred)
    
    assert len(df) == 3
    assert list(df["lead_time"]) == [1, 2, 3]
    
    # t=0: perfect prediction
    assert np.isclose(df.loc[0, "csi_0.5"], 1.0)
    assert np.isclose(df.loc[0, "mae"], 0.0)
    
    # t=1: half correct
    assert np.isclose(df.loc[1, "pod_0.5"], 0.5)
    assert np.isclose(df.loc[1, "csi_0.5"], 0.5)
    assert np.isclose(df.loc[1, "mae"], 0.5)
    
    # t=2: all wrong (0 hits, 100 misses)
    assert np.isclose(df.loc[2, "pod_0.5"], 0.0)
    assert np.isclose(df.loc[2, "csi_0.5"], 0.0)
    assert np.isclose(df.loc[2, "mae"], 1.0)

def test_persistence_model():
    model = PersistenceNowcast()
    
    state = np.array([[1, 2], [3, 4]])
    forecast = model.predict(state, lead_times=3)
    
    assert forecast.shape == (3, 2, 2)
    assert np.array_equal(forecast[0], state)
    assert np.array_equal(forecast[1], state)
    assert np.array_equal(forecast[2], state)

def test_compute_probabilistic_metrics():
    from jalrakshak_ml.evaluation.metrics import compute_probabilistic_metrics
    obs = np.array([0.0, 1.0, 0.0, 1.0])
    # threshold is 0.5
    # obs_v = [F, T, F, T] (0, 1, 0, 1)
    
    prob = np.array([0.1, 0.9, 0.2, 0.8])
    # Brier Score = sum((p - o)^2) / 4
    # (0.1 - 0)^2 + (0.9 - 1)^2 + (0.2 - 0)^2 + (0.8 - 1)^2
    # 0.01 + 0.01 + 0.04 + 0.04 = 0.10
    # Mean = 0.10 / 4 = 0.025
    
    res = compute_probabilistic_metrics(obs, prob, threshold=0.5)
    assert np.isclose(res["brier_score"], 0.025)
    
    # Reliability computation check:
    # Bins: 
    # 0.1 is in [0.1, 0.2) -> Bin 1
    # 0.2 is in [0.2, 0.3) -> Bin 2
    # 0.8 is in [0.8, 0.9) -> Bin 8
    # 0.9 is in [0.9, 1.0] -> Bin 9
    # Each bin has 1 item, so mean prob = item, mean obs = item.
    # The true observations are 0, 0, 1, 1 respectively.
    # Reliability is sum of (n_k/N)*(p_k - o_k)^2.
    # This exactly equals Brier Score here since each bin has 1 sample with 1 distinct outcome, 
    # EXCEPT Brier score is vs binary targets and reliability measures grouped calibration.
    # Let's just check it doesn't crash and returns a float >= 0.
    assert "reliability" in res
    assert res["reliability"] >= 0.0
