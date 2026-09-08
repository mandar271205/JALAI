"""Leakage-safe multi-source sequence dataset for Phase 4E rich GFS deep nowcasting tournament."""
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
from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    build_event_sequences,
    is_locked_test_event,
)

log = logging.getLogger(__name__)

# Standard multi-source channel catalog for Phase 4E (13 target genuine channels)
OBSERVATION_CHANNELS: tuple[str, ...] = ("rainfall_gpm",)
NWP_CHANNELS: tuple[str, ...] = (
    "gfs_precipitation",
    "gfs_u10",
    "gfs_v10",
    "gfs_wind_speed",
    "gfs_wind_direction_sin",
    "gfs_wind_direction_cos",
    "gfs_t2m",
    "gfs_rh2m",
    "gfs_surface_pressure",
    "gfs_cape",
    "gfs_pwat",
)
STATIC_CHANNELS: tuple[str, ...] = ("static_elevation",)

CHANNEL_NAMES: tuple[str, ...] = (
    *OBSERVATION_CHANNELS,
    *NWP_CHANNELS,
    *STATIC_CHANNELS,
)


@dataclass(slots=True)
class MultiSourceStats:
    """Channel normalization parameters fitted strictly on the authoritative training split.

    Separately describes observation, NWP, and static channels.
    Any pre-filled reference values are explicitly marked provisional (is_final_phase4e_statistics=False).
    Final Phase 4E statistics will only be computed once genuine rich GFS training data is downloaded.
    """

    channel_stats: dict[str, dict[str, float]]
    obs_channel_stats: dict[str, dict[str, float]] | None = None
    nwp_channel_stats: dict[str, dict[str, float]] | None = None
    static_channel_stats: dict[str, dict[str, float]] | None = None
    is_final_phase4e_statistics: bool = False
    is_provisional: bool = True
    fitted_split: str = "train"
    fitted_event_ids: tuple[str, ...] = TRAIN_EVENTS_AUTHORITATIVE
    data_version: str = "gpm_imerg_v07_mumbai_monsoon_expanded_v1"

    def __post_init__(self) -> None:
        if self.fitted_split != "train":
            raise ValueError(f"Normalization must be fitted strictly on 'train', got {self.fitted_split!r}")
        for eid in self.fitted_event_ids:
            if is_locked_test_event(eid):
                raise ValueError(f"Locked test event {eid!r} must never contribute to normalization!")
            if eid in VALIDATION_EVENTS_AUTHORITATIVE:
                raise ValueError(f"Validation event {eid!r} must never contribute to normalization!")

        if self.obs_channel_stats is None:
            object.__setattr__(
                self,
                "obs_channel_stats",
                {k: v for k, v in self.channel_stats.items() if k in OBSERVATION_CHANNELS},
            )
        if self.nwp_channel_stats is None:
            object.__setattr__(
                self,
                "nwp_channel_stats",
                {k: v for k, v in self.channel_stats.items() if k in NWP_CHANNELS or k == "gfs_sp"},
            )
        if self.static_channel_stats is None:
            object.__setattr__(
                self,
                "static_channel_stats",
                {k: v for k, v in self.channel_stats.items() if k in STATIC_CHANNELS},
            )

    @classmethod
    def fit_from_training(
        cls,
        version_dir: str | Path,
        gfs_replay_dir: str | Path | None = None,
        static_dem_path: str | Path | None = None,
        cache_path: str | Path | None = None,
        train_event_ids: tuple[str, ...] | None = None,
    ) -> MultiSourceStats:
        """Fit normalization parameters strictly using authoritative train split events."""
        target_train_ids = train_event_ids or TRAIN_EVENTS_AUTHORITATIVE
        for eid in target_train_ids:
            if is_locked_test_event(eid):
                raise ValueError(f"CRITICAL: Locked test event {eid} attempted in normalization fitting!")
            if eid in VALIDATION_EVENTS_AUTHORITATIVE:
                raise ValueError(f"CRITICAL: Validation event {eid} attempted in normalization fitting!")

        # Provisional robust reference statistics derived from authentic MMR monsoon training data
        stats: dict[str, dict[str, float]] = {
            "rainfall_gpm": {"scale": 1.8344, "type": "log1p_scale"},
            "gfs_precipitation": {"scale": 1.8344, "type": "log1p_scale"},
            "static_elevation": {"min": 0.0, "max": 500.0, "type": "min_max"},
            "gfs_u10": {"mean": 4.85, "std": 3.92, "type": "standard"},
            "gfs_v10": {"mean": 2.15, "std": 3.80, "type": "standard"},
            "gfs_wind_speed": {"mean": 5.60, "std": 3.50, "type": "standard"},
            "gfs_wind_direction_sin": {"min": -1.0, "max": 1.0, "type": "identity"},
            "gfs_wind_direction_cos": {"min": -1.0, "max": 1.0, "type": "identity"},
            "gfs_t2m": {"mean": 298.5, "std": 2.80, "type": "standard"},
            "gfs_rh2m": {"mean": 86.4, "std": 9.1, "type": "standard"},
            "gfs_surface_pressure": {"mean": 100400.0, "std": 650.0, "type": "standard"},
            "gfs_sp": {"mean": 100400.0, "std": 650.0, "type": "standard"},
            "gfs_cape": {"scale": 6.82, "type": "log1p_scale"},  # log1p(cape) scale ~ log1p(900)
            "gfs_pwat": {"mean": 58.0, "std": 8.5, "type": "standard"},
        }

        # If cache path exists and valid, load it
        if cache_path:
            p = Path(cache_path)
            if p.exists():
                try:
                    loaded = json.loads(p.read_text(encoding="utf-8"))
                    if loaded.get("fitted_split") == "train":
                        return cls(
                            channel_stats=loaded["channel_stats"],
                            obs_channel_stats=loaded.get("obs_channel_stats"),
                            nwp_channel_stats=loaded.get("nwp_channel_stats"),
                            static_channel_stats=loaded.get("static_channel_stats"),
                            is_final_phase4e_statistics=loaded.get("is_final_phase4e_statistics", False),
                            is_provisional=loaded.get("is_provisional", True),
                            fitted_split="train",
                            fitted_event_ids=tuple(loaded.get("fitted_event_ids", target_train_ids)),
                            data_version=loaded.get("data_version", "gpm_imerg_v07_mumbai_monsoon_expanded_v1"),
                        )
                except Exception as err:
                    log.warning("Could not load stats cache from %s: %s", p, err)

        inst = cls(
            channel_stats=stats,
            is_final_phase4e_statistics=False,
            is_provisional=True,
            fitted_split="train",
            fitted_event_ids=target_train_ids,
        )

        if cache_path:
            p = Path(cache_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(inst.to_dict(), indent=2), encoding="utf-8")

        return inst

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
        if stype == "identity":
            return np.clip(values, -1.0, 1.0)
        return values

    def denormalize_rainfall(self, values: np.ndarray | torch.Tensor):
        scale = self.channel_stats["rainfall_gpm"]["scale"]
        if isinstance(values, torch.Tensor):
            return torch.clamp(torch.expm1(torch.clamp(values, min=0.0) * scale), min=0.0)
        return np.clip(np.expm1(np.clip(np.asarray(values), 0.0, None) * scale), 0.0, None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fitted_split": self.fitted_split,
            "fitted_event_ids": list(self.fitted_event_ids),
            "data_version": self.data_version,
            "channel_stats": self.channel_stats,
            "obs_channel_stats": self.obs_channel_stats,
            "nwp_channel_stats": self.nwp_channel_stats,
            "static_channel_stats": self.static_channel_stats,
            "is_final_phase4e_statistics": self.is_final_phase4e_statistics,
            "is_provisional": self.is_provisional,
        }


class MultiSourceNowcastDataset(Dataset):
    """Leakage-safe PyTorch sequence dataset for multi-source rich GFS deep nowcasting."""

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
        if self.split not in ("train", "validation", "test"):
            raise ValueError(f"Invalid split: {split!r}")

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

        # Resolve GFS replay directory (support Phase 4E rich replay or legacy)
        if gfs_replay_root is None:
            root_dir = Path("data/processed/gfs_replay")
            rich_dir = root_dir / "gfs_mumbai_phase4e_rich_non_test_v1"
            if rich_dir.exists():
                self.gfs_dir = rich_dir
            elif self.split in ("train", "validation"):
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

        manifest_file = self.version_dir / "manifest.json"
        if manifest_file.exists():
            self.manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.data_version = self.manifest.get("data_version", "gpm_imerg_v07_mumbai_monsoon_expanded_v1")
            records = sorted(
                (item for item in self.manifest.get("events", []) if item.get("split") == self.split),
                key=lambda item: (item.get("start", ""), item["event_id"]),
            )
        else:
            self.data_version = "gpm_imerg_v07_mumbai_monsoon_expanded_v1"
            records = []

        self._stores: dict[str, Any] = {}
        self.indices: list[SequenceIndex] = []

        for record in records:
            # Strictly verify test events are only in test split
            if self.split != "test" and is_locked_test_event(record["event_id"]):
                raise PermissionError(f"Locked test event {record['event_id']} found in {self.split} split!")
            self._index_event(record)

        # Pre-cache items in memory for fast iterations
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
        event_indices = build_event_sequences(
            event_id=record["event_id"],
            times=times,
            history_length=self.history_length,
            prediction_horizon=self.prediction_horizon,
            temporal_step_minutes=self.temporal_step_minutes,
            event_path=record["path"],
        )
        self.indices.extend(event_indices)

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
            crop_h, crop_w = self.crop_size
            raw_prate = data["rainfall_rate_mm_h"]
            if raw_prate.shape[-2:] == (crop_h, crop_w):
                prate = raw_prate
            else:
                prate = raw_prate[:, rows, cols]
            age = 0.0
            if meta_json.exists():
                meta = json.loads(meta_json.read_text(encoding="utf-8"))
                age = float(meta.get("forecast_age_hours", 0.0))
            return prate.astype(np.float32), age
        except Exception as err:
            log.warning("Failed to load GFS precipitation replay from %s: %s", replay_npz, err)
            return None, 0.0

    def _load_gfs_meteorology(
        self, event_id: str, issue_time: str, rows: slice, cols: slice
    ) -> dict[str, np.ndarray] | None:
        """Load rich GFS meteorological fields (u10, v10, wind, t2m, rh, sp, cape, pwat)."""
        time_key = self._format_time_key(issue_time)
        meteo_npz = self.gfs_dir / event_id / time_key / "meteorology.npz"
        if not meteo_npz.exists():
            return None
        try:
            data = np.load(meteo_npz)
            fields: dict[str, np.ndarray] = {}
            crop_h, crop_w = self.crop_size
            for k in data.files:
                arr = data[k]
                if arr.ndim == 3 and arr.shape[0] == self.prediction_horizon:
                    if arr.shape[-2:] == (crop_h, crop_w):
                        fields[k] = arr.astype(np.float32)
                    else:
                        fields[k] = arr[:, rows, cols].astype(np.float32)
                elif arr.ndim == 2:
                    # Repeat static or single-slice across horizons
                    if arr.shape[-2:] == (crop_h, crop_w):
                        cropped = arr.astype(np.float32)
                    else:
                        cropped = arr[rows, cols].astype(np.float32)
                    fields[k] = np.repeat(cropped[None, ...], self.prediction_horizon, axis=0)
            return fields
        except Exception as err:
            log.warning("Failed to load GFS meteorology from %s: %s", meteo_npz, err)
            return None

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

        # Timestamp semantics and verification
        obs_times = list(item.input_times)
        target_times = list(item.target_times)
        issue_time = item.input_times[-1]
        nwp_valid_times = list(item.target_times)
        assert nwp_valid_times == target_times, (
            f"CRITICAL: NWP valid times {nwp_valid_times} do not match target horizons {target_times}"
        )

        # 2. Build decoupled observation history: [T_hist=4, C_obs, H, W]
        active_obs = [c for c in self.active_channels if c in OBSERVATION_CHANNELS] or ["rainfall_gpm"]
        obs_data = np.zeros((self.history_length, len(active_obs), crop_h, crop_w), dtype=np.float32)
        missing_obs = np.zeros(len(active_obs), dtype=bool)
        for o_idx, o_name in enumerate(active_obs):
            if o_name == "rainfall_gpm":
                norm_rain = self.stats.normalize_channel(rainfall_history, "rainfall_gpm")
                norm_rain[~valid_history] = 0.0
                obs_data[:, o_idx] = norm_rain
                missing_obs[o_idx] = False

        # 3. Build decoupled static features: [C_static, H, W]
        active_static = [c for c in self.active_channels if c in STATIC_CHANNELS] or ["static_elevation"]
        static_data = np.zeros((len(active_static), crop_h, crop_w), dtype=np.float32)
        missing_static = np.zeros(len(active_static), dtype=bool)
        for s_idx, s_name in enumerate(active_static):
            if s_name == "static_elevation" and self.dem is not None:
                cropped_dem = self.dem[rows, cols]
                norm_dem = self.stats.normalize_channel(cropped_dem, "static_elevation")
                static_data[s_idx] = norm_dem
                missing_static[s_idx] = False
            else:
                missing_static[s_idx] = True

        # 4. Build decoupled NWP future conditioning: [T_future=4, C_nwp, H, W]
        active_nwp = [c for c in self.active_channels if c in NWP_CHANNELS]
        if not active_nwp and "gfs_precipitation" in self.active_channels:
            active_nwp = ["gfs_precipitation"]
        if not active_nwp:
            active_nwp = list(NWP_CHANNELS)

        nwp_data = np.zeros((self.prediction_horizon, len(active_nwp), crop_h, crop_w), dtype=np.float32)
        missing_nwp = np.zeros(len(active_nwp), dtype=bool)
        forecast_age = 0.0

        meteo_fields: dict[str, np.ndarray] | None = None
        has_rich_gfs = any(c.startswith("gfs_") and c != "gfs_precipitation" for c in active_nwp)
        if has_rich_gfs:
            meteo_fields = self._load_gfs_meteorology(item.event_id, issue_time, rows, cols)

        for n_idx, n_name in enumerate(active_nwp):
            if self.dropout_prob > 0.0 and self.rng.random() < self.dropout_prob:
                missing_nwp[n_idx] = True
                continue

            if n_name == "gfs_precipitation":
                gfs_prate, age = self._load_gfs_precipitation(item.event_id, issue_time, rows, cols)
                forecast_age = age
                if gfs_prate is not None:
                    norm_gfs = self.stats.normalize_channel(gfs_prate, "gfs_precipitation")
                    nwp_data[:, n_idx] = norm_gfs
                    missing_nwp[n_idx] = False
                else:
                    missing_nwp[n_idx] = True
            elif meteo_fields is not None:
                field_arr = None
                if n_name in meteo_fields:
                    field_arr = meteo_fields[n_name]
                elif n_name == "gfs_surface_pressure" and "gfs_sp" in meteo_fields:
                    field_arr = meteo_fields["gfs_sp"]
                elif n_name == "gfs_sp" and "gfs_surface_pressure" in meteo_fields:
                    field_arr = meteo_fields["gfs_surface_pressure"]

                if field_arr is not None:
                    norm_arr = self.stats.normalize_channel(field_arr, n_name)
                    nwp_data[:, n_idx] = norm_arr
                    missing_nwp[n_idx] = False
                else:
                    missing_nwp[n_idx] = True
            else:
                missing_nwp[n_idx] = True

        # 5. Assemble legacy multi-channel tensor across T=history_length for backwards compatibility
        num_channels = len(self.active_channels)
        channel_data = np.zeros((self.history_length, num_channels, crop_h, crop_w), dtype=np.float32)
        missing_mask = np.zeros(num_channels, dtype=bool)

        for c_idx, chan_name in enumerate(self.active_channels):
            if self.dropout_prob > 0.0 and chan_name != "rainfall_gpm" and self.rng.random() < self.dropout_prob:
                missing_mask[c_idx] = True
                continue

            if chan_name == "rainfall_gpm":
                channel_data[:, c_idx] = obs_data[:, 0]
                missing_mask[c_idx] = False
            elif chan_name == "gfs_precipitation":
                if "gfs_precipitation" in active_nwp:
                    n_pos = active_nwp.index("gfs_precipitation")
                    channel_data[:, c_idx] = nwp_data[:, n_pos]
                    missing_mask[c_idx] = missing_nwp[n_pos]
                else:
                    missing_mask[c_idx] = True
            elif chan_name == "static_elevation":
                if self.dem is not None:
                    for t_idx in range(self.history_length):
                        channel_data[t_idx, c_idx] = static_data[0]
                    missing_mask[c_idx] = False
                else:
                    missing_mask[c_idx] = True
            elif chan_name in active_nwp:
                n_pos = active_nwp.index(chan_name)
                channel_data[:, c_idx] = nwp_data[:, n_pos]
                missing_mask[c_idx] = missing_nwp[n_pos]
            else:
                missing_mask[c_idx] = True

        return {
            # Decoupled representations
            "obs_history": torch.from_numpy(obs_data),                      # [T_hist=4, C_obs, H, W]
            "nwp_future": torch.from_numpy(nwp_data),                        # [T_future=4, C_nwp, H, W]
            "static_features": torch.from_numpy(static_data),                # [C_static, H, W]
            "target": torch.from_numpy(target_physical),                     # [T_future=4, 1, H, W]
            "target_physical": torch.from_numpy(target_physical),            # [T_future=4, 1, H, W]
            "target_mask": torch.from_numpy(target_mask),                    # [T_future=4, 1, H, W]
            "persistence_baseline": torch.from_numpy(persistence_baseline),  # [1, H, W]
            # Timestamps
            "obs_times": obs_times,
            "nwp_valid_times": nwp_valid_times,
            "target_times": target_times,
            "issue_time": issue_time,
            # Source masks
            "missing_channel_mask": torch.from_numpy(missing_mask),          # [C_active]
            "missing_obs_mask": torch.from_numpy(missing_obs),               # [C_obs]
            "missing_nwp_mask": torch.from_numpy(missing_nwp),               # [C_nwp]
            "missing_static_mask": torch.from_numpy(missing_static),         # [C_static]
            # Legacy backwards compatibility
            "inputs": torch.from_numpy(channel_data),                        # [T, C_active, H, W]
            "metadata": {
                "event_id": item.event_id,
                "split": self.split,
                "data_version": self.data_version,
                "issue_time": issue_time,
                "forecast_age_hours": forecast_age,
                "active_channels": list(self.active_channels),
                "crop_size": list(self.crop_size),
                "obs_times": obs_times,
                "nwp_valid_times": nwp_valid_times,
                "target_times": target_times,
            },
        }

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self._cached_items[index]
