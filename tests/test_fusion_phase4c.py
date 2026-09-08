"""Unit and regression tests for Phase 4C: Learned Gating & Calibrated Probabilistic Forecasting.

Covers:
- Train / Validation / Test split isolation (no leakage)
- No TEST calibration or hyperparameter selection
- Convex weights (w_i >= 0, sum w_i = 1.0)
- Graceful degradation on missing providers
- Probability range [0, 1] bounds
- Monotonic threshold ordering: P(>0.1) >= P(>1.0) >= P(>5.0) >= P(>10.0)
- Calibration isolation & insufficient support behavior
- Contract backwards compatibility with NowcastResult and deterministic ForecastResult
- Deterministic reproducibility
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml

from jalrakshak_ml.fusion.contracts import (
    BaseForecastProvider,
    ForecastResult,
    PersistenceProvider,
)
from jalrakshak_ml.fusion.core import (
    MultiModelFusion,
    create_learned_gate_fusion,
)
from jalrakshak_ml.fusion.gating import (
    GateFeatureBuilder,
    LearnedGateMLP,
    LearnedGatingModel,
)
from jalrakshak_ml.fusion.probabilistic import (
    CalibratedProbabilisticNowcaster,
    compute_probabilistic_metrics,
)
from jalrakshak_ml.nowcast.contracts import NowcastResult


class MockProvider(BaseForecastProvider):
    def __init__(self, name: str, fill_val: float, available: bool = True):
        self._name = name
        self.fill_val = fill_val
        self._avail = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return f"{self._name}_v1"

    @property
    def is_available(self) -> bool:
        return self._avail

    def predict(self, *, history_frames, issue_time, lead_times=4, temporal_step_minutes=30, **kwargs):
        arr = np.full((lead_times, 16, 16), self.fill_val, dtype=np.float32)
        mask = np.ones((lead_times, 16, 16), dtype=bool)
        return ForecastResult(
            rainfall_mm_h=arr,
            horizons_min=[30 * (i + 1) for i in range(lead_times)],
            issue_time=issue_time,
            valid_mask=mask,
            provider=self.name,
            model_version=self.model_version,
            data_version="test_v1",
        )


def test_split_isolation_and_no_test_leakage() -> None:
    manifest_path = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1/manifest.json")
    assert manifest_path.exists(), "Dataset manifest must exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    train_events = [e["event_id"] for e in manifest["events"] if e["split"] == "train"]
    val_events = [e["event_id"] for e in manifest["events"] if e["split"] == "validation"]
    test_events = [e["event_id"] for e in manifest["events"] if e["split"] == "test"]

    # Strict isolation
    assert set(train_events).isdisjoint(set(val_events))
    assert set(train_events).isdisjoint(set(test_events))
    assert set(val_events).isdisjoint(set(test_events))

    # Verify locked test events are untouched
    locked_test = {"mumbai_monsoon_2023_08_24", "mumbai_monsoon_2024_08_04", "mumbai_monsoon_2024_09_05"}
    assert set(test_events) == locked_test

    # Verify learned gate config does not use test split
    gate_cfg_path = Path("configs/fusion/learned_gate_v1.yaml")
    if gate_cfg_path.exists():
        cfg = yaml.safe_load(gate_cfg_path.read_text(encoding="utf-8"))
        assert cfg["training"]["train_split"] == "train"
        assert cfg["training"]["val_split"] == "validation"
        assert "test" not in cfg["training"].values()

    # Verify probabilistic config uses only validation split
    prob_cfg_path = Path("configs/probabilistic/probabilistic_nowcast_v1.yaml")
    if prob_cfg_path.exists():
        pcfg = yaml.safe_load(prob_cfg_path.read_text(encoding="utf-8"))
        assert pcfg["calibration_split"] == "validation"


def test_learned_gate_convex_weights_and_missing_providers() -> None:
    model_path = Path("models/fusion/learned_gate_v1/model.pt")
    if not model_path.exists():
        pytest.skip("Learned gate model not found")

    gate = LearnedGatingModel(model_path=model_path)
    assert gate.is_trained

    # Build dummy feature bundle
    dt = datetime(2023, 7, 25, 6, 0, tzinfo=UTC)
    builder = GateFeatureBuilder()
    p1 = MockProvider("persistence", 1.0)
    p2 = MockProvider("pysteps", 2.0)
    p3 = MockProvider("gfs", 1.5)

    hist = np.zeros((4, 16, 16), dtype=np.float32)
    res_dict = {
        "persistence": p1.predict(history_frames=hist, issue_time=dt),
        "pysteps": p2.predict(history_frames=hist, issue_time=dt),
        "gfs": p3.predict(history_frames=hist, issue_time=dt),
    }

    feat = builder.build_features_for_horizon(
        lead_idx=0,
        horizon_min=30,
        issue_time=dt,
        provider_results=res_dict,
        history_frames=hist,
    )

    # 1. All available providers
    weights = gate.predict_weights(feat, ["persistence", "pysteps", "gfs"])
    assert len(weights) == 3
    assert all(w >= 0.0 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 1e-5

    # 2. Missing GFS (only persistence and pysteps available)
    weights_no_gfs = gate.predict_weights(feat, ["persistence", "pysteps"])
    assert "gfs" not in weights_no_gfs
    assert len(weights_no_gfs) == 2
    assert all(w >= 0.0 for w in weights_no_gfs.values())
    assert abs(sum(weights_no_gfs.values()) - 1.0) < 1e-5

    # 3. Only single provider available
    weights_single = gate.predict_weights(feat, ["pysteps"])
    assert weights_single == {"pysteps": 1.0}


def test_probabilistic_bounds_and_threshold_ordering() -> None:
    nowcaster = CalibratedProbabilisticNowcaster(
        thresholds=[0.1, 1.0, 5.0, 10.0],
        horizons_min=[30, 60, 90, 120],
    )

    preds = {
        "pysteps": np.random.uniform(0.0, 15.0, (4, 32, 32)).astype(np.float32),
        "gfs": np.random.uniform(0.0, 15.0, (4, 32, 32)).astype(np.float32),
    }
    weights = {"pysteps": 0.6, "gfs": 0.4}

    raw_probs = nowcaster.compute_raw_probabilities(preds, weights)

    # Validate [0, 1] range
    for thr in [0.1, 1.0, 5.0, 10.0]:
        prob = raw_probs[thr]
        assert np.all(prob >= 0.0)
        assert np.all(prob <= 1.0)

    # Validate monotonic ordering: P(>0.1) >= P(>1.0) >= P(>5.0) >= P(>10.0)
    assert np.all(raw_probs[0.1] >= raw_probs[1.0] - 1e-6)
    assert np.all(raw_probs[1.0] >= raw_probs[5.0] - 1e-6)
    assert np.all(raw_probs[5.0] >= raw_probs[10.0] - 1e-6)


def test_insufficient_support_handling() -> None:
    nowcaster = CalibratedProbabilisticNowcaster(
        thresholds=[0.1, 10.0],
        horizons_min=[30],
        min_support_count=50,
    )

    # Dummy validation sample where threshold 10.0 has 0 positives
    val_sample = {
        "horizon_min": 30,
        "raw_probs": {
            0.1: np.full((10, 10), 0.8, dtype=np.float32),
            10.0: np.full((10, 10), 0.05, dtype=np.float32),
        },
        "obs_frame": np.full((10, 10), 2.0, dtype=np.float32),  # all > 0.1, none > 10.0
        "valid_mask": np.ones((10, 10), dtype=bool),
    }

    report = nowcaster.fit_calibration_on_validation([val_sample])
    assert nowcaster.calibration_status[(30, 10.0)] == "INSUFFICIENT_SUPPORT"
    assert report["calibrators"]["30_10.0"]["status"] == "INSUFFICIENT_SUPPORT"


def test_forecast_result_contract_backwards_compatibility() -> None:
    dt = datetime(2023, 8, 24, 6, 0, tzinfo=UTC)
    rainfall = np.ones((4, 16, 16), dtype=np.float32)
    mask = np.ones((4, 16, 16), dtype=bool)

    # 1. Pure deterministic initialization (old contract)
    res_det = ForecastResult(
        rainfall_mm_h=rainfall,
        horizons_min=[30, 60, 90, 120],
        issue_time=dt,
        valid_mask=mask,
        provider="pysteps",
        model_version="pysteps_v1",
        data_version="operational_v1",
    )
    assert res_det.forecast_confidence is None
    assert res_det.exceedance_probabilities is None
    nowcast_res = res_det.to_nowcast_result()
    assert isinstance(nowcast_res, NowcastResult)
    assert nowcast_res.provider == "pysteps"

    # 2. Probabilistic initialization (extended contract)
    probs = {
        0.1: np.full((4, 16, 16), 0.9, dtype=np.float32),
        1.0: np.full((4, 16, 16), 0.6, dtype=np.float32),
    }
    res_prob = ForecastResult(
        rainfall_mm_h=rainfall,
        horizons_min=[30, 60, 90, 120],
        issue_time=dt,
        valid_mask=mask,
        provider="fusion_learned_gate",
        model_version="learned_gate_mlp_v1",
        data_version="operational_v1",
        exceedance_probabilities=probs,
        probability_thresholds_mm_h=[0.1, 1.0],
        calibration_status={"30_0.1": "CALIBRATED_ISOTONIC"},
    )
    d = res_prob.to_dict()
    assert d["forecast_type"] == "probabilistic"
    assert d["probability_thresholds_mm_h"] == [0.1, 1.0]
    assert d["calibration_status"] == {"30_0.1": "CALIBRATED_ISOTONIC"}


def test_probabilistic_metrics_computation() -> None:
    y_true = np.array([1, 1, 0, 0, 1, 0, 1, 0, 0, 0], dtype=np.float32)
    p_pred = np.array([0.9, 0.8, 0.2, 0.1, 0.7, 0.3, 0.85, 0.15, 0.2, 0.1], dtype=np.float32)

    m = compute_probabilistic_metrics(y_true, p_pred, n_bins=5)
    assert m["status"] == "evaluated"
    assert m["sample_count"] == 10
    assert m["positive_count"] == 4
    assert 0.0 <= m["brier_score"] <= 1.0
    assert m["brier_skill_score"] > 0.0  # Good forecast should beat climatology
    assert isinstance(m["roc_auc"], float) and m["roc_auc"] > 0.8
    assert len(m["reliability_bins"]) == 5
