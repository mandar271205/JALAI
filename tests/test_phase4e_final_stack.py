from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader, Dataset

from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.experiments import apply_declared_mask
from jalrakshak_ml.deep_nowcast.final_contracts import (
    NWP_CHANNEL_ORDER,
    FinalNormalization,
    differentiable_nonnegative,
    validate_separated_inputs,
)
from jalrakshak_ml.deep_nowcast.final_dataset import Phase4EFinalDataset, SourceDropoutPolicy
from jalrakshak_ml.deep_nowcast.final_evaluation import (
    aggregate_deep_seeds,
    evaluate_validation_events,
    paired_event_bootstrap,
)
from jalrakshak_ml.deep_nowcast.final_runner import FinalValidationRunner, RunnerConfig
from jalrakshak_ml.deep_nowcast.final_tournament import (
    REQUIRED_MODELS,
    persistence_predictor,
    run_common_validation_tournament,
)
from jalrakshak_ml.deep_nowcast.phase4e_prepare import freeze_winner
from jalrakshak_ml.deep_nowcast.splits import (
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
)
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster


def _tensors(batch: int = 1):
    return (
        torch.rand(batch, 4, 1, 128, 128),
        torch.rand(batch, 4, 11, 128, 128),
        torch.rand(batch, 1, 128, 128),
        torch.rand(batch, 1, 128, 128),
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ConvLSTMNowcasterV3(input_channels=13, hidden_channels=(8, 8)),
        lambda: UNetConvGRUNowcaster(input_channels=13, base_channels=4, bottleneck_channels=8),
        lambda: STAttentionNowcasterV1(input_channels=13, embed_dim=16, num_heads=2),
    ],
)
def test_final_models_exact_separated_contract(factory):
    obs, nwp, static, baseline = _tensors()
    model = factory().eval()
    with torch.no_grad():
        output = model(
            obs_history=obs,
            nwp_future=nwp,
            static_features=static,
            persistence_baseline=baseline,
        )
    assert output.shape == (1, 4, 1, 128, 128)
    assert torch.all(output >= 0)
    with pytest.raises((TypeError, ValueError)):
        model(
            obs_history=obs,
            nwp_future=nwp[:, :3],
            static_features=static,
            persistence_baseline=baseline,
        )
    with pytest.raises(TypeError):
        model(obs_history=obs, nwp_future=nwp, static_features=static, target=output)


def test_final_parameter_counts_are_compact_and_locked():
    models = {
        "convlstm_v3": ConvLSTMNowcasterV3(input_channels=13),
        "unet_convgru_v1": UNetConvGRUNowcaster(input_channels=13),
        "st_attention_nowcaster_v1": STAttentionNowcasterV1(input_channels=13),
    }
    counts = {
        name: sum(parameter.numel() for parameter in model.parameters())
        for name, model in models.items()
    }
    assert counts == {
        "convlstm_v3": 121052,
        "unet_convgru_v1": 236308,
        "st_attention_nowcaster_v1": 134204,
    }
    assert all(count < 300_000 for count in counts.values())


def _normalization(path: Path, *, final: bool = True):
    groups = {
        "obs_history": ["rainfall_gpm"],
        "nwp_future": list(NWP_CHANNEL_ORDER),
        "static_features": ["static_elevation"],
    }
    payload = {
        "normalization_version": "phase4e_train_only_v1" if final else "legacy",
        "status": "PASS",
        "audit_passed": True,
        "fitted_split": "train",
        "fitted_event_ids": list(TRAIN_EVENTS_AUTHORITATIVE),
        "channel_order": groups,
        "statistics": {
            group: {channel: {"mean": 0.0, "std": 1.0} for channel in channels}
            for group, channels in groups.items()
        },
        "validation_opened": False,
        "locked_test_opened": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_final_normalization_accepts_only_exact_final_artifact(tmp_path):
    good = tmp_path / "normalization.json"
    payload = _normalization(good)
    loaded = FinalNormalization.load(good)
    assert loaded.artifact == payload
    with pytest.raises(ValueError, match="SHA-256"):
        FinalNormalization.load(good, expected_sha256="0" * 64)
    legacy = tmp_path / "legacy.json"
    _normalization(legacy, final=False)
    with pytest.raises(ValueError, match="legacy|Legacy"):
        FinalNormalization.load(legacy)
    payload["channel_order"]["nwp_future"] = list(reversed(NWP_CHANNEL_ORDER))
    good.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="channel order"):
        FinalNormalization.load(good)


def test_tensor_contract_rejects_nonfinite_and_wrong_channels():
    obs, nwp, static, baseline = _tensors()
    validate_separated_inputs(obs, nwp, static, baseline)
    with pytest.raises(ValueError, match="shape"):
        validate_separated_inputs(obs, nwp[:, :, :10], static, baseline)
    obs[0, 0, 0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        validate_separated_inputs(obs, nwp, static, baseline)
    assert differentiable_nonnegative(torch.tensor(0.0)).item() < 0.1


def test_dataset_api_cannot_construct_test_and_dropout_is_labeled(tmp_path):
    with pytest.raises(PermissionError, match="train or validation"):
        Phase4EFinalDataset(
            tmp_path,
            tmp_path,
            tmp_path / "dem.npy",
            tmp_path / "norm.json",
            replay_audit_path=tmp_path / "replay.json",
            channel_audit_path=tmp_path / "channels.json",
            split="test",
        )
    with pytest.raises(ValueError, match="labeled"):
        SourceDropoutPolicy(nwp_probability=0.2)


def test_train_crop_reproducible_and_validation_crop_deterministic():
    train = object.__new__(Phase4EFinalDataset)
    train.split = "train"
    train.seed = 26071
    first = train._crop("event", "2024-01-01T00:00:00+00:00")
    second = train._crop("event", "2024-01-01T00:00:00+00:00")
    assert first == second
    assert first[0].stop - first[0].start == 128
    validation = object.__new__(Phase4EFinalDataset)
    validation.split = "validation"
    validation.seed = 26071
    center = validation._crop("event", "2024-01-01T00:00:00+00:00")
    assert (center[0].start, center[1].start) == (64, 64)


def test_ablation_mask_metadata_never_calls_zero_real_meteorology():
    obs, nwp, static, baseline = _tensors()
    batch = {
        "obs_history": obs,
        "nwp_future": nwp,
        "static_features": static,
        "persistence_baseline": baseline,
        "missing_obs_mask": torch.zeros(1, 1, dtype=torch.bool),
        "missing_nwp_mask": torch.zeros(1, 11, dtype=torch.bool),
        "missing_static_mask": torch.zeros(1, 1, dtype=torch.bool),
    }
    result = apply_declared_mask(batch, "B_remove_wind_group", training_policy=True)
    assert result.metadata["zero_is_mask_not_measurement"] is True
    assert result.metadata["replacement_information_used"] is False
    assert result.tensors["missing_nwp_mask"].sum().item() == 5


def test_support_aware_metrics_and_seed_aggregation():
    events = {}
    for position, event_id in enumerate(("event_a", "event_b", "event_c")):
        target = np.zeros((1, 4, 1, 4, 4), dtype=np.float32)
        target[..., : position + 1] = 1.0
        events[event_id] = (target.copy(), target, np.ones_like(target, dtype=bool))
    report = evaluate_validation_events(events)
    assert (
        report["overall"]["horizons"]["30"]["thresholds"]["10.0"]["status"]
        == "INSUFFICIENT_SUPPORT"
    )
    aggregated = aggregate_deep_seeds(
        {26071: {"mae": 1.0}, 26072: {"mae": 2.0}, 26073: {"mae": 3.0}}
    )
    assert aggregated["aggregate"]["mae"]["mean"] == 2.0
    comparison = paired_event_bootstrap(
        {"a": 1.0, "b": 2.0, "c": 3.0},
        {"a": 2.0, "b": 3.0, "c": 4.0},
        iterations=100,
    )
    assert comparison["estimate_candidate_minus_reference"] == -1.0
    assert comparison["number_of_bootstrap_units"] == 3
    assert comparison["pixel_independence_assumed"] is False


def test_threshold_frequency_bias_is_reported_and_support_gated():
    observed = np.ones((1, 4, 1, 5, 5), dtype=np.float32)
    predicted = observed.copy()
    mask = np.ones_like(observed, dtype=bool)
    report = evaluate_validation_events(
        {"event_a": (predicted, observed, mask), "event_b": (predicted, observed, mask)}
    )
    threshold = report["overall"]["horizons"]["30"]["thresholds"]["1.0"]
    assert threshold["status"] == "OK"
    assert threshold["bias"] == 1.0


def test_common_tournament_uses_identical_validation_samples():
    class ValidationDataset(Dataset):
        split = "validation"
        nwp_channel_order = NWP_CHANNEL_ORDER

        def __init__(self):
            self.indices = [
                SimpleNamespace(event_id=event_id) for event_id in VALIDATION_EVENTS_AUTHORITATIVE
            ]

        def __len__(self):
            return 3

        def __getitem__(self, index):
            event_id = VALIDATION_EVENTS_AUTHORITATIVE[index]
            target = torch.ones(4, 1, 2, 2)
            return {
                "persistence_baseline": torch.ones(1, 2, 2),
                "target_physical": target,
                "target_mask": torch.ones_like(target, dtype=torch.bool),
                "metadata": {"event_id": event_id, "issue_time": f"issue-{index}"},
            }

    loader = DataLoader(ValidationDataset(), batch_size=1, shuffle=False)
    predictors = {name: persistence_predictor for name in REQUIRED_MODELS}
    report = run_common_validation_tournament(loader, predictors)
    assert set(report["models"]) == REQUIRED_MODELS
    assert report["paired_common_samples"] is True
    assert report["locked_test_accessed"] is False


def test_checkpoint_atomicity_and_winner_freeze_gate(tmp_path):
    runner = FinalValidationRunner(
        RunnerConfig(tmp_path / "checkpoints"),
        git_sha="a" * 40,
        config_hash="b" * 64,
        normalization_hash="c" * 64,
        replay_manifest_hash="d" * 64,
    )
    checkpoint = tmp_path / "checkpoint.pt"
    runner.atomic_checkpoint({"epoch": 1}, checkpoint)
    assert checkpoint.is_file() and not checkpoint.with_suffix(".pt.part").exists()
    with pytest.raises(ValueError, match="incomplete"):
        runner.validate_resume_checkpoint({"compatibility": {}}, {})
    required_checkpoint_keys = (
        "model",
        "optimizer",
        "scheduler",
        "scaler",
        "epoch",
        "best_mae",
        "best_epoch",
        "stale",
        "rng_state",
        "compatibility",
    )
    complete = {key: {} for key in required_checkpoint_keys}
    complete["compatibility"] = {"model_version": "v1"}
    runner.validate_resume_checkpoint(complete, {"model_version": "v1"})
    with pytest.raises(ValueError, match="incompatible"):
        runner.validate_resume_checkpoint(complete, {"model_version": "v2"})

    prerequisites = {
        "genuine_full_non_test_replay": True,
        "replay_audit": True,
        "real_channel_audit": True,
        "train_only_normalization": True,
        "multiseed_training": True,
        "validation_tournament": True,
        "required_ablations": True,
        "required_source_dropout_evaluation": True,
        "locked_test_clean": True,
    }
    selection = {
        "winning_model": "convlstm_v3",
        "architecture": "ConvLSTMNowcasterV3",
        "checkpoint_hashes": {str(seed): "e" * 64 for seed in (26071, 26072, 26073)},
        "seeds": [26071, 26072, 26073],
        "trained_models": {
            model: [26071, 26072, 26073]
            for model in ("convlstm_v3", "unet_convgru_v1", "st_attention_nowcaster_v1")
        },
        "validation_metrics": {"mae": 1.0},
        "selection_rule": "pre_registered_validation_rule_only",
        "replay_manifest_hash": "f" * 64,
        "normalization_hash": "1" * 64,
        "audit_hashes": {"replay": "2" * 64, "channels": "3" * 64},
        "config_hashes": {"training": "4" * 64},
        "git_commit": "a" * 40,
        "parameter_count": 100,
        "locked_test_accessed": False,
    }
    manifest = freeze_winner(selection, prerequisites, tmp_path / "winner.json")
    assert manifest["locked_test_automatically_run"] is False
    with pytest.raises(FileExistsError):
        freeze_winner(selection, prerequisites, tmp_path / "winner.json")
    contaminated = dict(prerequisites, locked_test_clean=False)
    with pytest.raises(RuntimeError, match="locked"):
        freeze_winner(selection, contaminated, tmp_path / "other.json")
