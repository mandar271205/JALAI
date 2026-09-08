from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
import zarr
from torch.utils.data import DataLoader, SequentialSampler, WeightedRandomSampler

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.dataset import (
    LogRainNormalizer,
    RainfallSequenceDataset,
    build_dataloaders,
    sequence_sampling_weights,
    sequence_target_maxima,
)
from jalrakshak_ml.deep_nowcast.evaluate import evaluate_heldout
from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
from jalrakshak_ml.deep_nowcast.losses import HeavyRainAwareLoss
from jalrakshak_ml.deep_nowcast.residual_convlstm import (
    PersistenceResidualConvLSTMNowcaster,
    reconstruct_persistence_residual,
)
from jalrakshak_ml.deep_nowcast.train import compute_validation_score, train_model
from jalrakshak_ml.deep_nowcast.verification import pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


def _datasets(version_dir):
    normalizer = LogRainNormalizer.fit_from_version(version_dir)
    datasets = {
        split: RainfallSequenceDataset(
            version_dir,
            split=split,
            history_length=4,
            prediction_horizon=4,
            crop_size=[4, 4],
            normalizer=normalizer,
        )
        for split in ("train", "validation", "test")
    }
    return datasets, normalizer


def test_masked_invalid_values_do_not_affect_heavy_rain_loss():
    criterion = HeavyRainAwareLoss(
        thresholds_mm_h=[1.0, 5.0, 10.0],
        weights=[1.0, 2.0, 6.0, 10.0],
        mse_weight=0.1,
    )
    target = torch.tensor([0.5, 12.0])
    mask = torch.tensor([True, False])
    reference = criterion(torch.tensor([1.5, 12.0]), target, mask)
    corrupted = criterion(torch.tensor([1.5, -10000.0]), target, mask)
    assert torch.equal(reference, corrupted)


def test_piecewise_physical_intensity_weights_are_exact():
    criterion = HeavyRainAwareLoss(
        thresholds_mm_h=[1.0, 5.0, 10.0],
        weights=[1.0, 2.0, 6.0, 10.0],
    )
    target = torch.tensor([0.0, 0.999, 1.0, 4.999, 5.0, 9.999, 10.0])
    assert torch.equal(
        criterion.intensity_weights(target),
        torch.tensor([1.0, 1.0, 2.0, 2.0, 6.0, 6.0, 10.0]),
    )


def test_sequence_sampling_weights_and_target_only_maxima(phase3_version_dir):
    datasets, _ = _datasets(phase3_version_dir)
    maxima = sequence_target_maxima(datasets["train"])
    assert np.allclose(maxima, [1.7, 1.8, 1.9])
    weights = sequence_sampling_weights(np.array([0.5, 1.0, 4.0, 5.0, 10.0]))
    assert np.array_equal(weights, [1.0, 2.0, 2.0, 4.0, 6.0])


def test_only_training_loader_uses_weighted_sampler(phase3_version_dir):
    datasets, _ = _datasets(phase3_version_dir)
    loaders, _ = build_dataloaders(
        datasets,
        {
            "seed": 7,
            "batch_size": 1,
            "num_workers": 0,
            "sampling": {
                "enabled": True,
                "thresholds_mm_h": [1.0, 5.0, 10.0],
                "weights": [1.0, 2.0, 4.0, 6.0],
                "replacement": True,
            },
        },
    )
    assert isinstance(loaders["train"].sampler, WeightedRandomSampler)
    assert isinstance(loaders["validation"].sampler, SequentialSampler)
    assert isinstance(loaders["test"].sampler, SequentialSampler)


def test_residual_reconstruction_and_non_negative_output():
    baseline = torch.tensor([[[[3.0, 1.0]]]])
    residual = torch.tensor([[[[[2.0, -4.0]]], [[[1.0, 0.5]]]]])
    reconstructed = reconstruct_persistence_residual(baseline, residual)
    expected = torch.tensor([[[[[5.0, 0.0]]], [[[4.0, 1.5]]]]])
    assert torch.equal(reconstructed, expected)
    model = PersistenceResidualConvLSTMNowcaster(
        input_channels=1,
        hidden_channels=[2],
        num_layers=1,
        output_horizons=2,
        head_channels=2,
    )
    prediction = model(torch.zeros(1, 4, 1, 2, 2), torch.ones(1, 1, 2, 2))
    assert torch.equal(prediction, torch.ones_like(prediction))
    assert torch.all(prediction >= 0)


def test_pooled_contingency_counts_and_mask_are_exact():
    evaluator = NowcastEvaluator(thresholds=[5.0])
    obs = np.array([[[6.0, 6.0, 0.0, 0.0]]])
    pred = np.array([[[6.0, 0.0, 6.0, 999.0]]])
    mask = np.array([[[True, True, True, False]]])
    rows = evaluator.evaluate_sequence(obs, pred, valid_mask=mask).to_dict(orient="records")
    pooled = pool_metric_rows([rows], [5.0])["overall"]
    assert pooled["hits_5.0"] == 1
    assert pooled["misses_5.0"] == 1
    assert pooled["false_alarms_5.0"] == 1
    assert pooled["correct_negatives_5.0"] == 0
    assert pooled["valid_pixels"] == 3
    assert np.isclose(pooled["pod_5.0"], 0.5)
    assert np.isclose(pooled["far_5.0"], 0.5)
    assert np.isclose(pooled["csi_5.0"], 1 / 3)


def test_validation_score_rewards_heavy_skill_and_handles_no_events():
    config = {
        "heavy_threshold_mm_h": 5.0,
        "weights": {"mae": 1.0, "csi": 2.0, "pod": 1.0, "far": 0.5},
    }
    weak = {
        "overall": {"mae": 1.0, "csi_5.0": 0.1, "pod_5.0": 0.1, "far_5.0": 0.8}
    }
    strong = {
        "overall": {"mae": 0.8, "csi_5.0": 0.4, "pod_5.0": 0.5, "far_5.0": 0.3}
    }
    no_heavy = {
        "overall": {"mae": 0.5, "csi_5.0": None, "pod_5.0": None, "far_5.0": None}
    }
    assert compute_validation_score(strong, config) > compute_validation_score(weak, config)
    assert np.isfinite(compute_validation_score(no_heavy, config))


class _PersistenceLikeModel:
    model_version = "mask-test"
    checkpoint_path = Path("mask-test.pt")
    checkpoint_hash = "mask-test"

    def predict(self, history, lead_times):
        return np.broadcast_to(history[-1, 0], (lead_times, *history.shape[-2:])).copy()


def test_heldout_evaluation_excludes_finite_target_mask_false_cells(
    phase3_version_dir,
    monkeypatch,
):
    test_store = zarr.open(str(phase3_version_dir / "events" / "storm_test.zarr"), mode="a")
    test_store["rainfall"][:, 2, 2] = 999.0
    test_store["valid_mask"][:, 2, 2] = False
    assert not np.asarray(test_store["valid_mask"][:, 2, 2]).any()
    monkeypatch.setattr(
        PystepsNowcast,
        "predict",
        lambda self, history, lead_times: np.broadcast_to(
            history[-1], (lead_times, *history[-1].shape)
        ).copy(),
    )
    datasets, _ = _datasets(phase3_version_dir)
    report = evaluate_heldout(datasets["test"], _PersistenceLikeModel(), max_samples=1)
    expected = 4 * (4 * 4 - 1)
    assert report["masking"]["common_valid_pixels"] == expected
    assert report["providers"]["convlstm"]["overall"]["valid_pixels"] == expected


def test_v2_checkpoint_contains_score_metrics_epoch_and_loads(
    phase3_version_dir,
    tmp_path,
):
    datasets, normalizer = _datasets(phase3_version_dir)
    model = PersistenceResidualConvLSTMNowcaster(
        input_channels=1,
        hidden_channels=[2],
        num_layers=1,
        output_horizons=4,
        head_channels=2,
    )
    outcome = train_model(
        model,
        DataLoader(datasets["train"], batch_size=1),
        DataLoader(datasets["validation"], batch_size=1),
        normalizer=normalizer,
        output_dir=tmp_path / "v2",
        data_version="gpm_test_v1",
        model_version="convlstm_mumbai_heavyrain_v2_test",
        epochs=1,
        device="cpu",
        intensity_thresholds_mm_h=[1.0, 5.0, 10.0],
        intensity_weights=[1.0, 2.0, 6.0, 10.0],
        validation_score_config={
            "heavy_threshold_mm_h": 5.0,
            "weights": {"mae": 1.0, "csi": 2.0, "pod": 1.0, "far": 0.5},
        },
        early_stopping_patience=2,
        seed=7,
    )
    checkpoint = torch.load(outcome.best_checkpoint, map_location="cpu", weights_only=False)
    metadata = json.loads(outcome.metadata_json.read_text(encoding="utf-8"))
    for key in ("best_validation_score", "best_validation_metrics", "best_epoch"):
        assert key in checkpoint
        assert key in metadata
    provider = ConvLSTMInference(outcome.best_checkpoint, device="cpu")
    prediction = provider.predict(datasets["test"].get_raw(0)["inputs"])
    assert prediction.shape == (4, 4, 4)
    assert np.isfinite(prediction).all()


def test_fixture_split_events_remain_isolated(phase3_version_dir):
    datasets, _ = _datasets(phase3_version_dir)
    train_events = set(datasets["train"].event_ids)
    validation_events = set(datasets["validation"].event_ids)
    test_events = set(datasets["test"].event_ids)
    assert not train_events & validation_events
    assert not train_events & test_events
    assert not validation_events & test_events


def test_v2_config_preserves_production_event_isolation_contract():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "training"
        / "convlstm_mumbai_heavyrain_v2.yaml"
    )
    config = load_yaml(config_path)
    expected = config["data"]["expected_split_event_ids"]
    sets = [set(expected[split]) for split in ("train", "validation", "test")]
    assert sets == [
        {"mumbai_monsoon_2023_07_18"},
        {"mumbai_monsoon_2023_07_25"},
        {"mumbai_monsoon_2023_08_24"},
    ]
    assert not sets[0] & sets[1]
    assert not sets[0] & sets[2]
    assert not sets[1] & sets[2]
