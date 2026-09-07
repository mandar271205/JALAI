from pathlib import Path

import numpy as np

from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, RainfallSequenceDataset
from jalrakshak_ml.deep_nowcast.evaluate import evaluate_heldout
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


class PersistenceLikeConvLSTM:
    model_version = "test"
    checkpoint_path = Path("test.pt")
    checkpoint_hash = "abc123"

    def predict(self, history, lead_times):
        latest = history[-1, 0]
        return np.broadcast_to(latest, (lead_times, *latest.shape)).copy()


def test_phase3_evaluation_uses_same_samples_and_pooled_counts(
    phase3_version_dir, monkeypatch
):
    monkeypatch.setattr(
        PystepsNowcast,
        "predict",
        lambda self, history, lead_times: np.broadcast_to(
            history[-1], (lead_times, *history[-1].shape)
        ).copy(),
    )
    normalizer = LogRainNormalizer.fit_from_version(phase3_version_dir)
    dataset = RainfallSequenceDataset(
        phase3_version_dir,
        split="test",
        history_length=4,
        prediction_horizon=4,
        normalizer=normalizer,
    )
    report = evaluate_heldout(dataset, PersistenceLikeConvLSTM(), max_samples=1)
    assert report["sample_count"] == 1
    assert report["events"] == ["storm_test"]
    assert report["probabilistic_metrics"] == "NOT_APPLICABLE_DETERMINISTIC_FORECAST"
    persistence = report["providers"]["persistence"]["metrics"]
    convlstm = report["providers"]["convlstm"]["metrics"]
    assert persistence == convlstm
    assert persistence[0]["hits_0.1"] > 0
