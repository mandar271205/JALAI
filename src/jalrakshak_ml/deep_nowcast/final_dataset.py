"""Authoritative train/validation-only dataset for the final Phase 4E tournament."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import zarr
from torch.utils.data import Dataset

from .final_contracts import (
    CROP_SHAPE,
    GRID_SHAPE,
    NWP_CHANNEL_ORDER,
    FinalNormalization,
    sha256_file,
)
from .splits import (
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    build_event_sequences,
    is_locked_test_event,
)


@dataclass(frozen=True, slots=True)
class SourceDropoutPolicy:
    """Whole-source training dropout; zero values are masks, never fake meteorology."""

    observation_probability: float = 0.0
    nwp_probability: float = 0.0
    terrain_probability: float = 0.0
    trained_with_source_dropout: bool = False

    def __post_init__(self) -> None:
        values = (
            self.observation_probability,
            self.nwp_probability,
            self.terrain_probability,
        )
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError("Source-dropout probabilities must be in [0, 1]")
        if any(values) and not self.trained_with_source_dropout:
            raise ValueError("Nonzero dropout must be labeled trained_with_source_dropout=true")


def _require_passed_audit(path: str | Path, version: str) -> str:
    audit_path = Path(path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    if payload.get("audit_version") != version or not payload.get("audit_passed"):
        raise RuntimeError(f"Required audit has not passed: {audit_path}")
    if payload.get("locked_test_accessed", False):
        raise PermissionError(f"Audit reports locked-test access: {audit_path}")
    return sha256_file(audit_path)


class Phase4EFinalDataset(Dataset):
    """Load only genuine, audited post-replay train or validation samples.

    The normal API intentionally has no test split. Future locked-test evaluation must
    live behind a separate command and immutable winner manifest.
    """

    nwp_channel_order = NWP_CHANNEL_ORDER

    def __init__(
        self,
        dataset_root: str | Path,
        replay_root: str | Path,
        elevation_path: str | Path,
        normalization_path: str | Path,
        *,
        replay_audit_path: str | Path,
        channel_audit_path: str | Path,
        split: str,
        seed: int = 26071,
        crop_shape: tuple[int, int] = CROP_SHAPE,
        source_dropout: SourceDropoutPolicy | None = None,
        expected_normalization_hash: str | None = None,
    ) -> None:
        self.split = split.lower()
        if self.split not in {"train", "validation"}:
            raise PermissionError("Final dataset API permits only train or validation")
        self.dataset_root = Path(dataset_root)
        self.replay_root = Path(replay_root)
        self.elevation_path = Path(elevation_path)
        self.seed = int(seed)
        self.crop_shape = tuple(crop_shape)
        if self.crop_shape != CROP_SHAPE:
            raise ValueError(f"Final deep-training crop must be {CROP_SHAPE}")
        self.source_dropout = source_dropout or SourceDropoutPolicy()
        if self.split == "validation" and any(
            (
                self.source_dropout.observation_probability,
                self.source_dropout.nwp_probability,
                self.source_dropout.terrain_probability,
            )
        ):
            raise ValueError("Validation augmentation/dropout is prohibited")

        self.replay_audit_hash = _require_passed_audit(
            replay_audit_path, "phase4e_rich_replay_integrity_v1"
        )
        self.channel_audit_hash = _require_passed_audit(
            channel_audit_path, "phase4e_real_channels_v1"
        )
        self.stats = FinalNormalization.load(
            normalization_path, expected_sha256=expected_normalization_hash
        )
        self.normalization_hash = sha256_file(normalization_path)

        manifest_path = self.dataset_root / "manifest.json"
        replay_manifest_path = self.replay_root / "manifest.json"
        if not manifest_path.is_file() or not replay_manifest_path.is_file():
            raise FileNotFoundError("Dataset and replay manifests are required")
        self.dataset_manifest_hash = sha256_file(manifest_path)
        self.replay_manifest_hash = sha256_file(replay_manifest_path)
        replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
        if replay_manifest.get("execution_state") != "COMPLETE":
            raise RuntimeError("Replay manifest is not COMPLETE")
        if replay_manifest.get("locked_test_accessed", False):
            raise PermissionError("Replay manifest reports locked-test access")

        elevation = np.load(self.elevation_path, allow_pickle=False).astype(np.float32)
        if elevation.shape == (1, *GRID_SHAPE):
            elevation = elevation[0]
        self._validate_array("elevation", elevation, GRID_SHAPE, nonnegative=False)
        self.elevation = elevation

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowed_events = (
            set(TRAIN_EVENTS_AUTHORITATIVE)
            if self.split == "train"
            else set(VALIDATION_EVENTS_AUTHORITATIVE)
        )
        records = [
            entry for entry in manifest.get("events", []) if entry.get("split") == self.split
        ]
        if {entry.get("event_id") for entry in records} != allowed_events:
            raise ValueError(f"Manifest does not contain the authoritative {self.split} event set")
        if any(is_locked_test_event(str(entry.get("event_id"))) for entry in records):
            raise PermissionError("Locked test entered final dataset")

        self.indices = []
        self._event_paths: dict[str, str] = {}
        for record in records:
            event_id = record["event_id"]
            event_path = str(record["path"])
            store = zarr.open(str(self.dataset_root / event_path), mode="r")
            times = [str(value) for value in store["time"][:]]
            indices = build_event_sequences(event_id, times=times, event_path=event_path)
            if len(indices) != 17:
                raise ValueError(f"{event_id} must produce exactly 17 samples, got {len(indices)}")
            self.indices.extend(indices)
            self._event_paths[event_id] = event_path
        expected = 204 if self.split == "train" else 51
        if len(self.indices) != expected:
            raise ValueError(f"Expected {expected} {self.split} samples, got {len(self.indices)}")

    @staticmethod
    def _validate_array(
        name: str,
        array: np.ndarray,
        shape: tuple[int, ...],
        *,
        nonnegative: bool,
    ) -> None:
        if array.shape != shape:
            raise ValueError(f"{name} expected shape {shape}, got {array.shape}")
        if not np.isfinite(array).all():
            raise ValueError(f"{name} contains NaN or Inf")
        if nonnegative and (array < 0.0).any():
            raise ValueError(f"{name} contains invalid negative rainfall")

    @staticmethod
    def _issue_key(issue_time: str) -> str:
        dt = datetime.fromisoformat(issue_time)
        return dt.strftime("%Y%m%dT%H%MZ")

    def _crop(self, event_id: str, issue_time: str) -> tuple[slice, slice]:
        if self.split == "validation":
            start = ((GRID_SHAPE[0] - CROP_SHAPE[0]) // 2,) * 2
        else:
            digest = hashlib.sha256(f"{self.seed}:{event_id}:{issue_time}".encode()).digest()
            max_row = GRID_SHAPE[0] - CROP_SHAPE[0]
            max_col = GRID_SHAPE[1] - CROP_SHAPE[1]
            start = (
                int.from_bytes(digest[:4], "big") % (max_row + 1),
                int.from_bytes(digest[4:8], "big") % (max_col + 1),
            )
        return (
            slice(start[0], start[0] + CROP_SHAPE[0]),
            slice(start[1], start[1] + CROP_SHAPE[1]),
        )

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> dict[str, Any]:
        sample = self.indices[index]
        issue_time = sample.input_times[-1]
        rows, cols = self._crop(sample.event_id, issue_time)
        store = zarr.open(str(self.dataset_root / sample.event_path), mode="r")
        middle = sample.start_index + 4
        obs = np.asarray(store["rainfall"][sample.start_index : middle], dtype=np.float32)
        obs_mask = np.asarray(store["valid_mask"][sample.start_index : middle], dtype=bool)
        target = np.asarray(store["rainfall"][middle : middle + 4], dtype=np.float32)
        target_mask = np.asarray(store["valid_mask"][middle : middle + 4], dtype=bool)
        self._validate_array("obs_history", obs, (4, *GRID_SHAPE), nonnegative=True)
        self._validate_array("target", target, (4, *GRID_SHAPE), nonnegative=True)
        if not obs_mask.all() or not target_mask.all():
            raise ValueError("Final dataset rejects missing GPM cells; no silent imputation")

        issue_dir = self.replay_root / sample.event_id / self._issue_key(issue_time)
        metadata_path = issue_dir / "metadata.json"
        rain_path = issue_dir / "rainfall.npz"
        meteo_path = issue_dir / "meteorology.npz"
        if not all(path.is_file() for path in (metadata_path, rain_path, meteo_path)):
            raise FileNotFoundError(f"Incomplete replay issue: {issue_dir}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("event_id") != sample.event_id or metadata.get("split") != self.split:
            raise ValueError("Replay metadata event/split mismatch")
        if list(metadata.get("target_times", sample.target_times)) != list(sample.target_times):
            raise ValueError("Replay target-time alignment mismatch")
        if not metadata.get("source_provenance"):
            raise ValueError("Replay source provenance is required")

        with np.load(rain_path, allow_pickle=False) as rainfall_file:
            precip = np.asarray(rainfall_file["rainfall_rate_mm_h"], dtype=np.float32)
        self._validate_array("gfs_precipitation", precip, (4, *GRID_SHAPE), nonnegative=True)
        nwp_fields = [precip]
        with np.load(meteo_path, allow_pickle=False) as meteo:
            for channel in NWP_CHANNEL_ORDER[1:]:
                if channel not in meteo.files:
                    raise ValueError(f"Required NWP channel missing: {channel}")
                field = np.asarray(meteo[channel], dtype=np.float32)
                self._validate_array(channel, field, (4, *GRID_SHAPE), nonnegative=False)
                nwp_fields.append(field)
        nwp = np.stack(nwp_fields, axis=1)

        obs_crop = obs[:, None, rows, cols]
        target_crop = target[:, None, rows, cols]
        nwp_crop = nwp[:, :, rows, cols]
        static_crop = self.elevation[None, rows, cols]
        obs_norm = self.stats.normalize(obs_crop, channel="rainfall_gpm", group="obs_history")
        nwp_norm = np.stack(
            [
                self.stats.normalize(nwp_crop[:, pos], channel=name, group="nwp_future")
                for pos, name in enumerate(NWP_CHANNEL_ORDER)
            ],
            axis=1,
        )
        static_norm = self.stats.normalize(
            static_crop, channel="static_elevation", group="static_features"
        )

        dropout_key = f"dropout:{self.seed}:{sample.event_id}:{issue_time}".encode()
        dropout_rng = np.random.default_rng(
            int.from_bytes(hashlib.sha256(dropout_key).digest()[:8], "big")
        )
        dropped = {"observation": False, "nwp": False, "terrain": False}
        if self.split == "train":
            dropped = {
                "observation": dropout_rng.random() < self.source_dropout.observation_probability,
                "nwp": dropout_rng.random() < self.source_dropout.nwp_probability,
                "terrain": dropout_rng.random() < self.source_dropout.terrain_probability,
            }
        for key, array in (
            ("observation", obs_norm),
            ("nwp", nwp_norm),
            ("terrain", static_norm),
        ):
            if dropped[key]:
                array.fill(0.0)
        persistence = obs[-1:, rows, cols].copy()
        if dropped["observation"]:
            persistence.fill(0.0)

        return {
            "obs_history": torch.from_numpy(obs_norm.copy()),
            "obs_history_physical": torch.from_numpy(obs_crop.copy()),
            "nwp_future": torch.from_numpy(nwp_norm.copy()),
            "static_features": torch.from_numpy(static_norm.copy()),
            "target": torch.from_numpy(target_crop.copy()),
            "target_physical": torch.from_numpy(target_crop.copy()),
            "target_mask": torch.ones_like(torch.from_numpy(target_crop), dtype=torch.bool),
            "persistence_baseline": torch.from_numpy(persistence),
            "missing_obs_mask": torch.tensor([dropped["observation"]]),
            "missing_nwp_mask": torch.full((11,), dropped["nwp"], dtype=torch.bool),
            "missing_static_mask": torch.tensor([dropped["terrain"]]),
            "metadata": {
                "event_id": sample.event_id,
                "issue_time": issue_time,
                "target_times": list(sample.target_times),
                "split": self.split,
                "replay_issue_id": issue_dir.name,
                "replay_issue_path": str(issue_dir),
                "source_versions": metadata.get("source_versions", {}),
                "source_provenance": metadata["source_provenance"],
                "nwp_channel_order": list(NWP_CHANNEL_ORDER),
                "crop_origin": [rows.start, cols.start],
                "source_dropout": {
                    "trained_with_source_dropout": self.source_dropout.trained_with_source_dropout,
                    "dropped_sources": [name for name, value in dropped.items() if value],
                    "zero_is_mask_not_measurement": True,
                },
                "normalization_hash": self.normalization_hash,
                "replay_manifest_hash": self.replay_manifest_hash,
            },
        }
