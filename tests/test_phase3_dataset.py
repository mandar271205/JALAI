from datetime import datetime

import numpy as np
import torch

from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, RainfallSequenceDataset


def test_event_isolated_deterministic_sequences(phase3_version_dir):
    normalizer = LogRainNormalizer.fit_from_version(phase3_version_dir)
    datasets = {
        split: RainfallSequenceDataset(
            phase3_version_dir,
            split=split,
            history_length=4,
            prediction_horizon=4,
            input_channels=["rainfall"],
            crop_size=[4, 4],
            normalizer=normalizer,
        )
        for split in ("train", "validation", "test")
    }
    assert {name: len(value) for name, value in datasets.items()} == {
        "train": 3, "validation": 3, "test": 3
    }
    assert set(datasets["train"].event_ids).isdisjoint(datasets["validation"].event_ids)
    assert set(datasets["train"].event_ids).isdisjoint(datasets["test"].event_ids)
    sample = datasets["train"][0]
    assert sample["inputs"].shape == (4, 1, 4, 4)
    assert sample["target"].shape == (4, 1, 4, 4)
    assert sample["input_mask"].dtype == torch.bool
    assert max(map(datetime.fromisoformat, sample["metadata"]["input_times"])) < min(
        map(datetime.fromisoformat, sample["metadata"]["target_times"])
    )


def test_normalization_is_fit_only_on_train(phase3_version_dir):
    normalizer = LogRainNormalizer.fit_from_version(phase3_version_dir)
    assert normalizer.fitted_split == "train"
    assert normalizer.fitted_event_ids == ("storm_train",)
    train_scale = normalizer.scale
    assert train_scale < np.log1p(20.0)


def test_raw_metadata_and_masks_are_explicit(phase3_version_dir):
    normalizer = LogRainNormalizer.fit_from_version(phase3_version_dir)
    dataset = RainfallSequenceDataset(
        phase3_version_dir,
        split="train",
        history_length=4,
        prediction_horizon=4,
        normalizer=normalizer,
    )
    raw = dataset.get_raw(0)
    assert raw["input_mask"].shape == raw["inputs"].shape
    assert raw["target_mask"].shape == raw["target"].shape
    assert not raw["input_mask"][:, :, 0, 0].any()
    assert raw["metadata"]["event_id"] == "storm_train"
    assert raw["metadata"]["data_version"] == "gpm_test_v1"
