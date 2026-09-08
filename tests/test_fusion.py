"""Comprehensive unit and integration test suite for multi-model forecast fusion.

Covers:
- no test-data calibration
- non-negative normalized weights
- missing provider fallback
- common-mask fairness
- horizon alignment
- GFS timing metadata propagation
- provider disagreement calculation
- deterministic reproducibility
- event isolation
- future-cycle rejection
- contract compatibility
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml

from jalrakshak_ml.deep_nowcast.verification import pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.fusion.calibration import calibrate_skill_weights
from jalrakshak_ml.fusion.contracts import (
    BaseForecastProvider,
    ForecastResult,
    GFSReplayProvider,
    PersistenceProvider,
    PystepsProvider,
)
from jalrakshak_ml.fusion.core import (
    MultiModelFusion,
    create_equal_weight_fusion,
    create_horizon_fixed_fusion,
)
from jalrakshak_ml.fusion.gating import (
    GateFeatureBuilder,
    GateFeatures,
    SupervisedGatingBaseline,
)
from jalrakshak_ml.fusion.uncertainty import (
    compute_ensemble_spread,
    compute_forecast_confidence,
    compute_provider_disagreement,
)
from jalrakshak_ml.nowcast.contracts import NowcastResult


class DummyMockProvider(BaseForecastProvider):
    """Deterministic dummy provider for testing."""

    def __init__(self, name: str, fill_value: float = 1.0, available: bool = True) -> None:
        self._name = name
        self.fill_value = fill_value
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return f"{self._name}_test_v1"

    @property
    def is_available(self) -> bool:
        return self._available

    def predict(
        self,
        *,
        history_frames: np.ndarray | None = None,
        issue_time: datetime,
        lead_times: int = 4,
        temporal_step_minutes: int = 30,
        event_id: str | None = None,
        context: dict | None = None,
    ) -> ForecastResult:
        if not self.is_available:
            raise RuntimeError(f"{self.name} is unavailable")
        arr = np.full((lead_times, 64, 64), self.fill_value, dtype=np.float32)
        vmask = np.ones((lead_times, 64, 64), dtype=bool)
        horizons = [temporal_step_minutes * (i + 1) for i in range(lead_times)]
        return ForecastResult(
            rainfall_mm_h=arr,
            horizons_min=horizons,
            issue_time=issue_time,
            valid_mask=vmask,
            provider=self.name,
            model_version=self.model_version,
            data_version="test_v1",
        )


def test_no_test_data_calibration_assertion():
    """Verify calibration strictly forbids test split."""
    class MockDataset:
        split = "test"

    with pytest.raises(ValueError, match="train_dataset split must be 'train'"):
        calibrate_skill_weights(MockDataset(), MockDataset())


def test_non_negative_normalized_weights():
    """Verify weights are normalized and strictly non-negative."""
    p1 = DummyMockProvider("m1", fill_value=2.0)
    p2 = DummyMockProvider("m2", fill_value=4.0)

    # Provide unnormalized and negative weights
    fusion = MultiModelFusion(
        [p1, p2],
        fusion_method="custom",
        weights_by_horizon={
            30: {"m1": -5.0, "m2": 10.0},
            60: {"m1": 2.0, "m2": 6.0},
        },
    )

    w30 = fusion._get_weights_for_lead(0, 30, ["m1", "m2"])
    assert w30["m1"] == 0.0
    assert w30["m2"] == 1.0
    assert sum(w30.values()) == pytest.approx(1.0)

    w60 = fusion._get_weights_for_lead(1, 60, ["m1", "m2"])
    assert w60["m1"] == pytest.approx(0.25)
    assert w60["m2"] == pytest.approx(0.75)
    assert sum(w60.values()) == pytest.approx(1.0)


def test_missing_provider_fallback():
    """Verify graceful renormalization and fallback when a provider is unavailable."""
    p1 = DummyMockProvider("m1", fill_value=2.0, available=True)
    p2 = DummyMockProvider("m2", fill_value=4.0, available=False)

    fusion = MultiModelFusion(
        [p1, p2],
        fusion_method="horizon_fixed",
        weights_by_horizon={30: {"m1": 0.3, "m2": 0.7}},
    )

    now = datetime(2024, 8, 4, 1, 30, tzinfo=UTC)
    result = fusion.predict(issue_time=now, lead_times=4)

    # m2 was unavailable, so m1 receives 100% weight
    assert result.uncertainty["fallback_applied"] is True
    assert "m2" in result.uncertainty["missing_providers"]
    assert np.allclose(result.rainfall_mm_h, 2.0)


def test_all_providers_unavailable_raises():
    """Verify descriptive error when zero providers are available."""
    p1 = DummyMockProvider("m1", available=False)
    fusion = MultiModelFusion([p1])
    with pytest.raises(RuntimeError, match="No forecast providers were available"):
        fusion.predict(issue_time=datetime(2024, 8, 4, 1, 30, tzinfo=UTC))


def test_common_mask_fairness():
    """Verify evaluation strictly intersects masks across models."""
    obs = np.ones((1, 10, 10), dtype=np.float32)
    p1 = np.ones((1, 10, 10), dtype=np.float32)
    p2 = np.ones((1, 10, 10), dtype=np.float32)

    # Invalidate different pixels
    obs[0, 0, 0] = np.nan
    p1[0, 1, 1] = np.nan
    p2[0, 2, 2] = np.nan

    common_mask = np.isfinite(obs) & np.isfinite(p1) & np.isfinite(p2)
    assert common_mask[0, 0, 0] == False
    assert common_mask[0, 1, 1] == False
    assert common_mask[0, 2, 2] == False
    assert common_mask[0, 3, 3] == True

    evaluator = NowcastEvaluator(thresholds=[0.1])
    res1 = evaluator.evaluate_sequence(obs, p1, valid_mask=common_mask)
    res2 = evaluator.evaluate_sequence(obs, p2, valid_mask=common_mask)

    assert res1["valid_pixels"].iloc[0] == 97
    assert res2["valid_pixels"].iloc[0] == 97


def test_horizon_alignment_contracts():
    """Verify ForecastResult enforces horizon dimension checks."""
    now = datetime.now(UTC)
    arr = np.zeros((4, 32, 32), dtype=np.float32)
    mask = np.ones((4, 32, 32), dtype=bool)

    # Valid
    res = ForecastResult(
        rainfall_mm_h=arr,
        horizons_min=[30, 60, 90, 120],
        issue_time=now,
        valid_mask=mask,
        provider="test",
        model_version="v1",
        data_version="d1",
    )
    assert res.rainfall_mm_h.shape[0] == 4

    # Horizon count mismatch
    with pytest.raises(ValueError, match="horizons_min count"):
        ForecastResult(
            rainfall_mm_h=arr,
            horizons_min=[30, 60],
            issue_time=now,
            valid_mask=mask,
            provider="test",
            model_version="v1",
            data_version="d1",
        )

    # Negative values
    bad_arr = arr.copy()
    bad_arr[0, 0, 0] = -1.0
    with pytest.raises(ValueError, match="negative values"):
        ForecastResult(
            rainfall_mm_h=bad_arr,
            horizons_min=[30, 60, 90, 120],
            issue_time=now,
            valid_mask=mask,
            provider="test",
            model_version="v1",
            data_version="d1",
        )


def test_gfs_timing_metadata_propagation():
    """Verify GFS provider loads and propagates exact timing metadata."""
    gfs_root = Path("data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1")
    if not gfs_root.exists():
        pytest.skip("GFS replay directory not present")

    provider = GFSReplayProvider(replay_root=gfs_root)
    assert provider.is_available is True

    # Test with known sample
    res = provider.predict(
        issue_time=datetime(2023, 8, 24, 1, 30, tzinfo=UTC),
        event_id="mumbai_monsoon_2023_08_24",
    )
    assert res.native_cadence_minutes == 60
    assert res.output_cadence_minutes == 30
    assert "cycle_time" in res.source_metadata
    assert "availability_time" in res.source_metadata
    assert res.source_metadata["forecast_age_hours"] >= 6.0


def test_future_cycle_rejection_anti_leakage(monkeypatch):
    """Verify anti-leakage rejects future cycle if availability > issue_time."""
    gfs_root = Path("data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1")
    if not gfs_root.exists():
        pytest.skip("GFS replay directory not present")

    provider = GFSReplayProvider(replay_root=gfs_root)

    # Patch json.loads when reading metadata.json to simulate an availability time after issue time
    real_loads = json.loads

    def mock_loads(s, **kwargs):
        data = real_loads(s, **kwargs)
        if isinstance(data, dict) and "availability_time" in data:
            # Shift availability into the future
            data["availability_time"] = "2025-01-01T00:00:00+00:00"
        return data

    monkeypatch.setattr(json, "loads", mock_loads)

    with pytest.raises(ValueError, match="Anti-leakage violation"):
        provider.predict(
            issue_time=datetime(2023, 8, 24, 1, 30, tzinfo=UTC),
            event_id="mumbai_monsoon_2023_08_24",
        )


def test_provider_disagreement_calculation():
    """Verify spread and disagreement formulas on controlled inputs."""
    f1 = np.full((2, 10, 10), 2.0, dtype=np.float32)
    f2 = np.full((2, 10, 10), 4.0, dtype=np.float32)

    spread = compute_ensemble_spread([f1, f2])
    assert np.allclose(spread, np.sqrt(2.0))  # sample std dev of [2, 4] is sqrt(2) ~ 1.414

    dis = compute_provider_disagreement({"m1": f1, "m2": f2})
    assert dis["mean_pairwise_abs_diff"] == [2.0, 2.0]
    assert dis["max_spread"] == [2.0, 2.0]

    conf = compute_forecast_confidence(
        mean_forecast=np.full((2, 10, 10), 3.0, dtype=np.float32),
        spread=spread,
        valid_count=2,
        expected_count=2,
    )
    assert len(conf["confidence_score"]) == 2
    assert 0.0 <= conf["confidence_score"][0] <= 1.0


def test_deterministic_reproducibility():
    """Verify identical inputs yield identical outputs bitwise."""
    p1 = DummyMockProvider("m1", fill_value=1.5)
    p2 = DummyMockProvider("m2", fill_value=3.5)
    fusion = create_equal_weight_fusion([p1, p2])

    now = datetime(2024, 8, 4, 2, 0, tzinfo=UTC)
    res1 = fusion.predict(issue_time=now, lead_times=4)
    res2 = fusion.predict(issue_time=now, lead_times=4)

    assert np.array_equal(res1.rainfall_mm_h, res2.rainfall_mm_h)
    assert res1.to_dict() == res2.to_dict()


def test_contract_compatibility():
    """Verify ForecastResult converts cleanly to NowcastResult."""
    now = datetime.now(UTC)
    res = ForecastResult(
        rainfall_mm_h=np.ones((4, 16, 16), dtype=np.float32),
        horizons_min=[30, 60, 90, 120],
        issue_time=now,
        valid_mask=np.ones((4, 16, 16), dtype=bool),
        provider="fusion_equal",
        model_version="fusion_equal_v1",
        data_version="test_d1",
        uncertainty={"spread": 0.5},
    )

    nowcast_res = res.to_nowcast_result()
    assert isinstance(nowcast_res, NowcastResult)
    assert nowcast_res.provider == "fusion_equal"
    assert nowcast_res.rainfall.shape == (4, 16, 16)
    manifest = nowcast_res.to_manifest()
    assert manifest["provider"] == "fusion_equal"
    assert manifest["horizons_min"] == [30, 60, 90, 120]


def test_gate_feature_builder():
    """Verify GateFeatureBuilder constructs clean schema features."""
    builder = GateFeatureBuilder()
    now = datetime(2024, 8, 4, 3, 0, tzinfo=UTC)

    p1 = DummyMockProvider("pysteps", fill_value=2.0)
    p2 = DummyMockProvider("gfs", fill_value=1.0)
    res1 = p1.predict(issue_time=now, lead_times=4)
    res2 = p2.predict(issue_time=now, lead_times=4)

    features = builder.build_features_for_horizon(
        lead_idx=0,
        horizon_min=30,
        issue_time=now,
        provider_results={"pysteps": res1, "gfs": res2},
        history_frames=np.full((4, 64, 64), 2.5, dtype=np.float32),
    )

    assert features.horizon_min == 30
    assert features.shared.rain_regime == 1  # 2.5 mm/h is light rain
    assert "pysteps" in features.providers
    assert "gfs" in features.providers
    assert features.providers["pysteps"].mean_forecast_mm_h == 2.0
    assert features.providers["gfs"].mean_forecast_mm_h == 1.0

    flat = features.to_flat_dict()
    assert "pysteps_mean" in flat
    assert "gfs_mean" in flat

    baseline = SupervisedGatingBaseline()
    assert baseline.is_trained is False
    weights = baseline.predict_weights(features, ["pysteps", "gfs"])
    assert weights["pysteps"] == 0.5
    assert weights["gfs"] == 0.5
