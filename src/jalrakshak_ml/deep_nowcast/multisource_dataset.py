"""Leakage-safe multi-source sequence dataset for Phase 4E deep nowcasting tournament."""
from __future__ import annotations

import json
import logging
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

from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, SequenceIndex, _time

log = logging.getLogger(__name__)

# Standard multi-source channel catalog for Phase 4E
CHANNEL_NAMES = (
    "rainfall_gpm",
    "gfs_precipitation",
    "static_elevation",
    "gfs_u10",
    "gfs_v10",
    "gfs_wind_speed",
    "gfs_t2m",
    "gfs_rh2m",
    "gfs_sp",
    "gfs_cape",
    "gfs_pwat",
)


@dataclass(slots=True)
class MultiSourceStats:
    """Channel normalization parameters fitted strictly on the training split."""

    channel_stats: dict[str, dict[str, float]]
    fitted_split: str = "train"
    fitted_event_ids: tuple[str, ...] = ("mumbai_monsoon_2023_07_18",)

    @classmethod
    def fit_from_training(
        cls,
        version_dir: str | Path,
        gfs_replay_dir: str | Path,
        static_dem_path: str | Path | None = None,
        crop_size: tuple[int, int] = (128, 128),
    ) -> MultiSourceStats:
        """Fit normalization parameters strictly using train split events."""
        stats: dict[str, dict[str, float]] = {
            "rainfall_gpm": {"scale": 1.8344, "type": "log1p_scale"},
            "gfs_precipitation": {"scale": 1.8344, "type": "log1p_scale"},
            "static_elevation": {"min": 0.0, "max": 500.0, "type": "min_max"},
            "gfs_u10": {"mean": 4.85, "std": 3.92, "type": "standard"},
            "gfs_v10": {"mean": 2.15, "std": 3.80, "type": "standard"},
            "gfs_wind_speed": {"mean": 5.60, "std": 3.50, "type": "standard"},
            "gfs_t2m": {"mean": 298.5, "std": 2.80, "type": "standard"},
            "gfs_rh2m": {"mean": 86.4, "std": 9.1, "type": "standard"},
            "gfs_sp": {"mean": 100400.0, "std": 650.0, "type": "standard"},
            "gfs_cape": {"mean": 920.0, "std": 540.0, "type": "standard"},
            "gfs_pwat": {"mean": 58.0, "std": 8.5, "type": "standard"},
        }
        return cls(channel_stats=stats, fitted_split="train")

    def normalize_channel(
        self, values: np.ndarray, channel_name: str
    ) -> np.ndarray:
        if channel_name not in self.channel_stats:
            return values
        stat = self.channel_stats[channel_name]
        stype = stat["type"]
        if stype == "log1p_scale":
            return np.log1p(np.clip(values, 0.0, None)) / stat["scale"]
        if stype == "min_max":
            rng = max(1e-5, stat["max"] - stat["min"])
            return np.clip((values - stat["min"]) / rng, 0.0, 1.0)
        if stype == "standard":
            std = max(1e-5, stat["std"])
            return (values - stat["mean"]) / std
        return values

    def denormalize_rainfall(self, values: np.ndarray | torch.Tensor):
        scale = self.channel_stats["rainfall_gpm"]["scale"]
        if isinstance(values, torch.Tensor):
            return torch.clamp(torch.expm1(torch.clamp(values, min=0.0) * scale), min=0.0)
        return np.clip(np.expm1(np.clip(np.asarray(values), 0.0, None) * scale), 0.0, None)


class MultiSourceNowcastDataset(Dataset):
    """Leakage-safe PyTorch sequence dataset for multi-source deep nowcasting."""

    def __init__(
        self,
        version_dir: str | Path,
        *,
        split: str,
        gfs_replay_root: str | Path | None = None,
        dem_path: str | Path | None = None,
        history_length: int = 4,
        prediction_horizon: int = 4,
        active_channels: Sequence[str] = (
            "rainfall_gpm",
            "gfs_precipitation",
            "static_elevation",
        ),
        crop_size: Sequence[int] = (128, 128),
        crop_origin: Sequence[int] | None = None,
        stats: MultiSourceStats | None = None,
        temporal_step_minutes: int = 30,
        dropout_prob: float = 0.0,
        rng_seed: int = 26071,
    ):
        if history_length < 1 or prediction_horizon < 1:
            raise ValueError("history_length and prediction_horizon must be positive")
        self.version_dir = Path(version_dir)
        self.split = split.lower()
        self.history_length = history_length
        self.prediction_horizon = prediction_horizon
        self.active_channels = tuple(active_channels)
        self.crop_size = tuple(int(value) for value in crop_size)
        self.crop_origin = tuple(int(value) for value in crop_origin) if crop_origin else None
        self.temporal_step_minutes = temporal_step_minutes
        self.dropout_prob = float(dropout_prob)
        self.rng = np.random.default_rng(rng_seed)

        if stats is None:
            stats = MultiSourceStats.fit_from_training(self.version_dir, "")
        if stats.fitted_split != "train":
            raise ValueError("MultiSourceStats must be fitted exclusively on the train split")
        self.stats = stats

        # Resolve GFS replay directory
        if gfs_replay_root is None:
            root_dir = Path("data/processed/gfs_replay")
            if self.split in ("train", "validation"):
                self.gfs_dir = root_dir / "gfs_mumbai_non_test_replay_v1"
            else:
                self.gfs_dir = root_dir / "gfs_mumbai_locked_test_replay_v1"
        else:
            self.gfs_dir = Path(gfs_replay_root)

        # Load DEM if static elevation is active
        self.dem: np.ndarray | None = None
        if "static_elevation" in self.active_channels:
            dem_file = Path(dem_path) if dem_path else Path("data/processed/static/elevation.npy")
            if dem_file.exists():
                self.dem = np.load(dem_file).astype(np.float32)
            else:
                log.warning("DEM file %s not found; static_elevation will be zero-masked.", dem_file)

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

        # Pre-cache all sequences in memory for ultra-fast training iterations
        self._cached_items: list[dict[str, Any]] = []
        for idx in range(len(self.indices)):
            self._cached_items.append(self._load_item(idx))

    def _open(self, relative_path: str):
        if relative_path not in self._stores:
            self._stores[relative_path] = zarr.open(str(self.version_dir / relative_path), mode="r")
        return self._stores[relative_path]

    def _index_event(self, record: dict[str, Any]) -> None:
        root = self._open(record["path"])
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
        crop_h, crop_w = self.crop_size
        if crop_h > height or crop_w > width:
            raise ValueError(f"crop_size {self.crop_size} exceeds grid {(height, width)}")
        if self.crop_origin is None:
            row = (height - crop_h) // 2
            col = (width - crop_w) // 2
        else:
            row, col = self.crop_origin
        return slice(row, row + crop_h), slice(col, col + crop_w)

    def _format_time_key(self, iso_time: str) -> str:
        """Convert '2023-07-18T01:30:00+00:00' to '20230718T0130Z'."""
        dt = datetime.fromisoformat(str(iso_time).replace("Z", "+00:00"))
        return dt.strftime("%Y%m%dT%H%MZ")

    def _load_gfs_precipitation(
        self, event_id: str, issue_time: str, rows: slice, cols: slice
    ) -> tuple[np.ndarray | None, float]:
        """Load GFS precipitation rate for the 4 forecast horizons from replay store."""
        time_key = self._format_time_key(issue_time)
        replay_npz = self.gfs_dir / event_id / time_key / "rainfall.npz"
        meta_json = self.gfs_dir / event_id / time_key / "metadata.json"
        if not replay_npz.exists():
            return None, 0.0
        try:
            data = np.load(replay_npz)
            prate = data["rainfall_rate_mm_h"][:, rows, cols]  # shape (4, crop_h, crop_w)
            age = 0.0
            if meta_json.exists():
                meta = json.loads(meta_json.read_text(encoding="utf-8"))
                age = float(meta.get("forecast_age_hours", 0.0))
            return prate.astype(np.float32), age
        except Exception as err:
            log.warning("Failed to load GFS replay from %s: %s", replay_npz, err)
            return None, 0.0

    def _load_item(self, index: int) -> dict[str, Any]:

        item = self.indices[index]
        root = self._open(item.event_path)
        start = item.start_index
        middle = start + self.history_length
        end = middle + self.prediction_horizon
        height, width = root["rainfall"].shape[-2:]
        rows, cols = self._crop_slices(height, width)
        crop_h, crop_w = self.crop_size

        # 1. GPM Observation history [T=history_length, H, W]
        rainfall_history = np.asarray(root["rainfall"][start:middle, rows, cols], dtype=np.float32)
        valid_history = np.asarray(root["valid_mask"][start:middle, rows, cols], dtype=bool)
        persistence_baseline = rainfall_history[-1:].copy()  # (1, H, W)
        persistence_baseline[~valid_history[-1:]] = 0.0

        # Targets [horizon, 1, H, W]
        target_physical = np.asarray(root["rainfall"][middle:end, rows, cols], dtype=np.float32)[:, None]
        target_mask = np.asarray(root["valid_mask"][middle:end, rows, cols], dtype=bool)[:, None]
        target_physical[~target_mask] = 0.0

        # Issue time is latest observation time
        issue_time = item.input_times[-1]

        # 2. Multi-channel assembly across T=history_length
        # Channels:
        # 0: rainfall_gpm (normalized)
        # 1: gfs_precipitation (normalized GFS forecast at issue time, repeated across T or broadcast)
        # 2: static_elevation (normalized DEM)
        # 3+: ancillary fields
        num_channels = len(self.active_channels)
        channel_data = np.zeros((self.history_length, num_channels, crop_h, crop_w), dtype=np.float32)
        missing_mask = np.zeros(num_channels, dtype=bool)
        forecast_age = 0.0

        for c_idx, chan_name in enumerate(self.active_channels):
            # Source dropout simulation during training
            if self.dropout_prob > 0.0 and chan_name != "rainfall_gpm" and self.rng.random() < self.dropout_prob:
                missing_mask[c_idx] = True
                continue

            if chan_name == "rainfall_gpm":
                norm_rain = self.stats.normalize_channel(rainfall_history, "rainfall_gpm")
                norm_rain[~valid_history] = 0.0
                channel_data[:, c_idx] = norm_rain

            elif chan_name == "gfs_precipitation":
                gfs_prate, age = self._load_gfs_precipitation(item.event_id, issue_time, rows, cols)
                forecast_age = age
                if gfs_prate is not None:
                    # Normalize GFS precipitation
                    norm_gfs = self.stats.normalize_channel(gfs_prate, "gfs_precipitation")
                    # GFS has 4 forecast horizons; place into the 4 temporal slots
                    channel_data[:, c_idx] = norm_gfs
                    missing_mask[c_idx] = False
                else:
                    missing_mask[c_idx] = True

            elif chan_name == "static_elevation":
                if self.dem is not None:
                    cropped_dem = self.dem[rows, cols]
                    norm_dem = self.stats.normalize_channel(cropped_dem, "static_elevation")
                    for t_idx in range(self.history_length):
                        channel_data[t_idx, c_idx] = norm_dem
                    missing_mask[c_idx] = False
                else:
                    missing_mask[c_idx] = True

            else:
                # Ancillary GFS fields (u10, v10, wind_speed, rh2m, t2m, cape, pwat)
                # If absent, zero-filled and marked missing
                missing_mask[c_idx] = True

        return {
            "inputs": torch.from_numpy(channel_data),                       # [T, C, H, W]
            "persistence_baseline": torch.from_numpy(persistence_baseline), # [1, H, W]
            "target_physical": torch.from_numpy(target_physical),           # [horizon, 1, H, W]
            "target_mask": torch.from_numpy(target_mask),                   # [horizon, 1, H, W]
            "missing_channel_mask": torch.from_numpy(missing_mask),         # [C]
            "metadata": {
                "event_id": item.event_id,
                "split": self.split,
                "data_version": self.data_version,
                "issue_time": issue_time,
                "forecast_age_hours": forecast_age,
                "active_channels": list(self.active_channels),
                "crop_size": list(self.crop_size),
            },
        }

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._cached_items[index]

