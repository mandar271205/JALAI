"""Focused regressions for genuine GPM missingness in the Phase 4E stack."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import torch
import zarr

from jalrakshak_ml.deep_nowcast.dataset import SequenceIndex
from jalrakshak_ml.deep_nowcast.final_contracts import NWP_CHANNEL_ORDER
from jalrakshak_ml.deep_nowcast.final_dataset import (
    Phase4EFinalDataset,
    SourceDropoutPolicy,
)
from jalrakshak_ml.deep_nowcast.losses import MultiScalePiecewiseLoss
from jalrakshak_ml.deep_nowcast.phase4e_prepare import validate_gpm_mask_semantics


def test_legitimate_nan_at_invalid_gpm_pixel_is_accepted() -> None:
    rainfall = np.array([[1.0, np.nan]], dtype=np.float32)
    mask = np.array([[True, False]])

    checked_rainfall, checked_mask = validate_gpm_mask_semantics(
        rainfall, mask, context="test"
    )

    assert np.isnan(checked_rainfall[0, 1])
    assert np.array_equal(checked_mask, mask)


@pytest.mark.parametrize(
    ("rainfall", "mask", "message"),
    [
        (
            np.array([[np.nan]], dtype=np.float32),
            np.array([[True]]),
            "valid GPM pixel contains non-finite rainfall",
        ),
        (
            np.array([[0.0]], dtype=np.float32),
            np.array([[False]]),
            "invalid GPM pixel contains finite rainfall",
        ),
        (
            np.array([[-0.1]], dtype=np.float32),
            np.array([[True]]),
            "valid GPM pixel contains negative rainfall",
        ),
    ],
)
def test_gpm_mask_contract_rejects_inconsistent_or_negative_values(
    rainfall: np.ndarray, mask: np.ndarray, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_gpm_mask_semantics(rainfall, mask, context="test")


def test_gpm_mask_contract_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        validate_gpm_mask_semantics(
            np.ones((2, 2), dtype=np.float32),
            np.ones((2, 1), dtype=bool),
            context="test",
        )


class _IdentityLikeStats:
    def normalize(self, values: np.ndarray, *, group: str, channel: str) -> np.ndarray:
        del group, channel
        return (np.asarray(values, dtype=np.float32) - 1.0) / 2.0


def _build_dataset_item_fixture(
    tmp_path: Path,
) -> tuple[Phase4EFinalDataset, np.ndarray, np.ndarray]:
    dataset_root = tmp_path / "dataset"
    replay_root = tmp_path / "replay"
    event_id = "fixture_train_event"
    event_path = "fixture.zarr"
    source_path = dataset_root / event_path
    source_path.parent.mkdir(parents=True)

    rainfall = np.stack(
        [np.full((256, 256), float(frame + 1), dtype=np.float32) for frame in range(8)]
    )
    valid_mask = np.ones_like(rainfall, dtype=bool)
    valid_mask[:, 0, 0] = False
    valid_mask[:, 1, 1] = False
    rainfall[~valid_mask] = np.nan
    store = zarr.open(str(source_path), mode="w")
    store.create_dataset("rainfall", data=rainfall, shape=rainfall.shape, dtype=np.float32)
    store.create_dataset("valid_mask", data=valid_mask, shape=valid_mask.shape, dtype=bool)

    start = datetime(2021, 6, 18, tzinfo=UTC)
    times = tuple((start + timedelta(minutes=30 * i)).isoformat() for i in range(8))
    sequence = SequenceIndex(
        event_id=event_id,
        event_path=event_path,
        start_index=0,
        input_times=times[:4],
        target_times=times[4:],
    )
    issue_key = datetime.fromisoformat(times[3]).strftime("%Y%m%dT%H%MZ")
    issue_dir = replay_root / event_id / issue_key
    issue_dir.mkdir(parents=True)
    np.savez_compressed(
        issue_dir / "rainfall.npz",
        rainfall_rate_mm_h=np.ones((4, 256, 256), dtype=np.float32),
    )
    np.savez_compressed(
        issue_dir / "meteorology.npz",
        **{
            channel: np.ones((4, 256, 256), dtype=np.float32)
            for channel in NWP_CHANNEL_ORDER[1:]
        },
    )
    (issue_dir / "metadata.json").write_text(
        json.dumps(
            {
                "event_id": event_id,
                "split": "train",
                "target_times": list(times[4:]),
                "source_provenance": {"fixture": {"parser_state": "PASSED"}},
            }
        ),
        encoding="utf-8",
    )

    dataset = object.__new__(Phase4EFinalDataset)
    dataset.split = "train"
    dataset.dataset_root = dataset_root
    dataset.replay_root = replay_root
    dataset.indices = [sequence]
    dataset.seed = 26071
    dataset.crop_shape = (128, 128)
    dataset.source_dropout = SourceDropoutPolicy()
    dataset.stats = _IdentityLikeStats()
    dataset.elevation = np.ones((256, 256), dtype=np.float32)
    dataset.normalization_hash = "fixture-normalization-hash"
    dataset.replay_manifest_hash = "fixture-replay-hash"
    dataset._crop = lambda _event_id, _issue_time: (slice(0, 128), slice(0, 128))
    return dataset, rainfall.copy(), valid_mask.copy()


def test_final_dataset_finite_fills_model_tensors_and_preserves_exact_masks(
    tmp_path: Path,
) -> None:
    dataset, source_rainfall, source_mask = _build_dataset_item_fixture(tmp_path)

    item = dataset[0]

    for key in ("obs_history", "obs_history_physical", "target", "target_physical"):
        assert torch.isfinite(item[key]).all()
    expected_obs_mask = torch.from_numpy(source_mask[:4, None, :128, :128])
    expected_target_mask = torch.from_numpy(source_mask[4:, None, :128, :128])
    assert torch.equal(item["obs_valid_mask"], expected_obs_mask)
    assert torch.equal(item["target_mask"], expected_target_mask)
    assert torch.count_nonzero(item["obs_history"][~expected_obs_mask]) == 0
    assert torch.count_nonzero(item["obs_history_physical"][~expected_obs_mask]) == 0
    assert torch.count_nonzero(item["target"][~expected_target_mask]) == 0
    assert torch.count_nonzero(item["target_physical"][~expected_target_mask]) == 0

    source = zarr.open(str(dataset.dataset_root / "fixture.zarr"), mode="r")
    assert np.array_equal(np.asarray(source["rainfall"][:]), source_rainfall, equal_nan=True)
    assert np.array_equal(np.asarray(source["valid_mask"][:]), source_mask)


def test_masked_pixels_do_not_contribute_to_multiscale_loss() -> None:
    loss_fn = MultiScalePiecewiseLoss(coarse_scale_weight=1.0, pool_kernel=2)
    target = torch.zeros((1, 1, 1, 2, 2))
    prediction = target.clone()
    prediction[..., 0, 0] = 1000.0
    mask = torch.ones_like(target, dtype=torch.bool)
    mask[..., 0, 0] = False

    assert loss_fn(prediction, target, mask).item() == pytest.approx(0.0)


def test_partially_invalid_pooling_uses_valid_only_mean() -> None:
    loss_fn = MultiScalePiecewiseLoss(pool_kernel=2)
    target = torch.tensor([[[[[8.0, 0.0], [0.0, 0.0]]]]])
    prediction = torch.tensor([[[[[4.0, 0.0], [0.0, 0.0]]]]])
    mask = torch.tensor([[[[[True, False], [False, False]]]]])

    pooled_prediction, pooled_target, pooled_mask, support = loss_fn.masked_pool(
        prediction, target, mask
    )

    assert pooled_target.item() == pytest.approx(8.0)
    assert pooled_prediction.item() == pytest.approx(4.0)
    assert pooled_mask.item() is True
    assert support.item() == pytest.approx(1.0)


def test_all_invalid_coarse_block_has_zero_supervision() -> None:
    loss_fn = MultiScalePiecewiseLoss(coarse_scale_weight=1.0, pool_kernel=2)
    target = torch.zeros((1, 1, 1, 2, 2))
    prediction = torch.full_like(target, 99.0)
    mask = torch.zeros_like(target, dtype=torch.bool)

    pooled_prediction, pooled_target, pooled_mask, support = loss_fn.masked_pool(
        prediction, target, mask
    )

    assert pooled_prediction.item() == pytest.approx(0.0)
    assert pooled_target.item() == pytest.approx(0.0)
    assert pooled_mask.item() is False
    assert support.item() == pytest.approx(0.0)
    assert loss_fn(prediction, target, mask).item() == pytest.approx(0.0)
