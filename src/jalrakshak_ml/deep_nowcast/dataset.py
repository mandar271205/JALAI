"""Leakage-safe PyTorch sequence dataset for event-isolated rainfall data."""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import torch
import zarr
from torch.utils.data import Dataset

from jalrakshak_ml.config import load_yaml


def _time(value: str) -> datetime:
    return datetime.fromisoformat(str(value))


@dataclass(frozen=True, slots=True)
class SequenceIndex:
    event_id: str
    event_path: str
    start_index: int
    input_times: tuple[str, ...]
    target_times: tuple[str, ...]


@dataclass(slots=True)
class LogRainNormalizer:
    """Non-negative log scaling fitted exclusively on valid training pixels."""

    scale: float
    percentile: float = 99.5
    fitted_split: str = "train"
    fitted_event_ids: tuple[str, ...] = ()
    valid_pixel_count: int = 0

    @classmethod
    def fit_from_version(
        cls,
        version_dir: str | Path,
        *,
        split: str = "train",
        percentile: float = 99.5,
        max_samples: int = 1_000_000,
    ) -> LogRainNormalizer:
        if split != "train":
            raise ValueError("Normalization statistics may only be fitted on the training split")
        version_dir = Path(version_dir)
        manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
        records = [item for item in manifest["events"] if item["split"] == split]
        if not records:
            raise ValueError("No training events are available for normalization")
        samples: list[np.ndarray] = []
        total_valid = 0
        per_event_limit = max(1, max_samples // len(records))
        for record in records:
            root = zarr.open(str(version_dir / record["path"]), mode="r")
            rainfall = np.asarray(root["rainfall"][:], dtype=np.float32)
            mask = np.asarray(root["valid_mask"][:], dtype=bool) & np.isfinite(rainfall)
            values = np.clip(rainfall[mask], 0.0, None)
            total_valid += int(values.size)
            if values.size:
                stride = max(1, math.ceil(values.size / per_event_limit))
                samples.append(values[::stride])
        if not samples:
            raise ValueError("Training split has no valid rainfall pixels")
        sampled = np.concatenate(samples)
        log_scale = float(np.percentile(np.log1p(sampled), percentile))
        return cls(
            scale=max(log_scale, 1e-6),
            percentile=percentile,
            fitted_split=split,
            fitted_event_ids=tuple(item["event_id"] for item in records),
            valid_pixel_count=total_valid,
        )

    def transform(self, values: np.ndarray | torch.Tensor):
        if isinstance(values, torch.Tensor):
            return torch.log1p(torch.clamp(values, min=0.0)) / self.scale
        return np.log1p(np.clip(np.asarray(values), 0.0, None)) / self.scale

    def inverse(self, values: np.ndarray | torch.Tensor):
        if isinstance(values, torch.Tensor):
            return torch.clamp(torch.expm1(torch.clamp(values, min=0.0) * self.scale), min=0.0)
        return np.clip(np.expm1(np.clip(np.asarray(values), 0.0, None) * self.scale), 0.0, None)

    def transform_scalar(self, value: float) -> float:
        return float(np.log1p(max(0.0, value)) / self.scale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "log1p_percentile_scale",
            "scale": self.scale,
            "percentile": self.percentile,
            "fitted_split": self.fitted_split,
            "fitted_event_ids": list(self.fitted_event_ids),
            "valid_pixel_count": self.valid_pixel_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LogRainNormalizer:
        return cls(
            scale=float(value["scale"]),
            percentile=float(value.get("percentile", 99.5)),
            fitted_split=str(value.get("fitted_split", "train")),
            fitted_event_ids=tuple(value.get("fitted_event_ids", ())),
            valid_pixel_count=int(value.get("valid_pixel_count", 0)),
        )


class RainfallSequenceDataset(Dataset):
    """Deterministic windows that never cross an event or a temporal gap."""

    def __init__(
        self,
        version_dir: str | Path,
        *,
        split: str,
        history_length: int = 4,
        prediction_horizon: int = 4,
        input_channels: Sequence[str] = ("rainfall",),
        crop_size: Sequence[int] | None = None,
        crop_origin: Sequence[int] | None = None,
        normalizer: LogRainNormalizer,
        temporal_step_minutes: int = 30,
    ):
        if history_length < 1 or prediction_horizon < 1:
            raise ValueError("history_length and prediction_horizon must be positive")
        if normalizer.fitted_split != "train":
            raise ValueError("normalizer must have been fitted on the training split")
        self.version_dir = Path(version_dir)
        self.split = split.lower()
        self.history_length = history_length
        self.prediction_horizon = prediction_horizon
        self.input_channels = tuple(input_channels)
        self.normalizer = normalizer
        self.temporal_step_minutes = temporal_step_minutes
        self.crop_size = tuple(int(value) for value in crop_size) if crop_size else None
        self.crop_origin = tuple(int(value) for value in crop_origin) if crop_origin else None
        if not self.input_channels or "rainfall" not in self.input_channels:
            raise ValueError("Phase-3 inputs must include the rainfall channel")

        self.manifest = json.loads((self.version_dir / "manifest.json").read_text(encoding="utf-8"))
        self.data_version = self.manifest["data_version"]
        self._stores: dict[str, Any] = {}
        self.indices: list[SequenceIndex] = []
        records = sorted(
            (item for item in self.manifest["events"] if item["split"] == self.split),
            key=lambda item: (item["start"], item["event_id"]),
        )
        for record in records:
            self._index_event(record)

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.event_id for item in self.indices))

    def _open(self, relative_path: str):
        if relative_path not in self._stores:
            self._stores[relative_path] = zarr.open(str(self.version_dir / relative_path), mode="r")
        return self._stores[relative_path]

    def _index_event(self, record: dict[str, Any]) -> None:
        root = self._open(record["path"])
        for channel in self.input_channels:
            if channel not in root:
                raise KeyError(f"Input channel {channel!r} is missing from {record['path']}")
        times = [str(value) for value in root["time"][:]]
        window = self.history_length + self.prediction_horizon
        for start in range(len(times) - window + 1):
            candidate = times[start : start + window]
            deltas = [
                (_time(right) - _time(left)).total_seconds() / 60.0
                for left, right in pairwise(candidate)
            ]
            if any(delta != self.temporal_step_minutes for delta in deltas):
                continue
            self.indices.append(SequenceIndex(
                event_id=record["event_id"],
                event_path=record["path"],
                start_index=start,
                input_times=tuple(candidate[: self.history_length]),
                target_times=tuple(candidate[self.history_length :]),
            ))

    def __len__(self) -> int:
        return len(self.indices)

    def _crop_slices(self, height: int, width: int) -> tuple[slice, slice]:
        if self.crop_size is None:
            return slice(0, height), slice(0, width)
        crop_h, crop_w = self.crop_size
        if crop_h > height or crop_w > width:
            raise ValueError(f"crop_size {self.crop_size} exceeds grid {(height, width)}")
        if self.crop_origin is None:
            row = (height - crop_h) // 2
            col = (width - crop_w) // 2
        else:
            row, col = self.crop_origin
        if row < 0 or col < 0 or row + crop_h > height or col + crop_w > width:
            raise ValueError("crop_origin places the crop outside the grid")
        return slice(row, row + crop_h), slice(col, col + crop_w)

    def get_raw(self, index: int) -> dict[str, Any]:
        item = self.indices[index]
        root = self._open(item.event_path)
        start = item.start_index
        middle = start + self.history_length
        end = middle + self.prediction_horizon
        height, width = root["rainfall"].shape[-2:]
        rows, cols = self._crop_slices(height, width)

        channels = []
        channel_masks = []
        rainfall_valid = np.asarray(root["valid_mask"][start:middle, rows, cols], dtype=bool)
        for channel in self.input_channels:
            values = np.asarray(root[channel][start:middle, rows, cols], dtype=np.float32)
            mask = rainfall_valid if channel == "rainfall" else np.isfinite(values)
            channels.append(values)
            channel_masks.append(mask)
        inputs = np.stack(channels, axis=1)
        input_mask = np.stack(channel_masks, axis=1)
        target = np.asarray(root["rainfall"][middle:end, rows, cols], dtype=np.float32)[:, None]
        target_mask = np.asarray(root["valid_mask"][middle:end, rows, cols], dtype=bool)[:, None]
        return {
            "inputs": inputs,
            "target": target,
            "input_mask": input_mask,
            "target_mask": target_mask,
            "metadata": {
                "event_id": item.event_id,
                "split": self.split,
                "data_version": self.data_version,
                "input_times": list(item.input_times),
                "target_times": list(item.target_times),
                "issue_time": item.input_times[-1],
                "input_channels": list(self.input_channels),
            },
        }

    def __getitem__(self, index: int) -> dict[str, Any]:
        raw = self.get_raw(index)
        inputs = raw["inputs"].copy()
        rainfall_channel = self.input_channels.index("rainfall")
        inputs[:, rainfall_channel] = self.normalizer.transform(inputs[:, rainfall_channel])
        target = self.normalizer.transform(raw["target"])
        inputs[~raw["input_mask"]] = 0.0
        target[~raw["target_mask"]] = 0.0
        return {
            "inputs": torch.from_numpy(inputs.astype(np.float32)),
            "target": torch.from_numpy(target.astype(np.float32)),
            "input_mask": torch.from_numpy(raw["input_mask"]),
            "target_mask": torch.from_numpy(raw["target_mask"]),
            "metadata": raw["metadata"],
        }


def build_datasets_from_config(config_path: str | Path):
    config_path = Path(config_path).resolve()
    config = load_yaml(config_path)
    repo_root = config_path.parents[2]
    version_dir = repo_root / config["data"]["output_root"] / config["data"]["version"]
    dataset_cfg = config["dataset"]
    normalizer = LogRainNormalizer.fit_from_version(
        version_dir,
        percentile=float(dataset_cfg.get("normalization_percentile", 99.5)),
    )
    common = {
        "history_length": int(dataset_cfg["history_length"]),
        "prediction_horizon": int(dataset_cfg["prediction_horizon"]),
        "input_channels": dataset_cfg["input_channels"],
        "crop_size": dataset_cfg.get("crop_size"),
        "crop_origin": dataset_cfg.get("crop_origin"),
        "normalizer": normalizer,
        "temporal_step_minutes": int(config["data"]["temporal_step_minutes"]),
    }
    datasets = {
        split: RainfallSequenceDataset(version_dir, split=split, **common)
        for split in ("train", "validation", "test")
    }
    overlap = (
        set(datasets["train"].event_ids) & set(datasets["validation"].event_ids)
        | set(datasets["train"].event_ids) & set(datasets["test"].event_ids)
        | set(datasets["validation"].event_ids) & set(datasets["test"].event_ids)
    )
    if overlap:
        raise RuntimeError(f"Event leakage detected across splits: {sorted(overlap)}")
    return datasets, normalizer
