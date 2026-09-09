"""Execution-gated normalization, tournament, ablation, and model-freeze preparation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import zarr

from .multisource_dataset import NWP_CHANNELS, OBSERVATION_CHANNELS, STATIC_CHANNELS
from .splits import (
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    is_locked_test_event,
)


class RunningStats:
    def __init__(self):
        self.count = self.finite_count = 0
        self.mean = self.m2 = 0.0
        self.minimum = float("inf")
        self.maximum = float("-inf")

    def update(self, values: np.ndarray) -> None:
        array = np.asarray(values, dtype=np.float64)
        self.count += array.size
        finite = array[np.isfinite(array)]
        if not finite.size:
            return
        count, mean, variance = finite.size, float(finite.mean()), float(finite.var())
        delta, total = mean - self.mean, self.finite_count + count
        self.mean += delta * count / total
        self.m2 += variance * count + delta * delta * self.finite_count * count / total
        self.finite_count = total
        self.minimum = min(self.minimum, float(finite.min()))
        self.maximum = max(self.maximum, float(finite.max()))

    def result(self) -> dict[str, float | int]:
        if not self.finite_count:
            raise ValueError("Required channel has no finite real values")
        std = (self.m2 / self.finite_count) ** 0.5
        if std <= 1e-7:
            raise ValueError("Channel has near-zero variance; degenerate distribution rejected")
        return {
            "count": self.count,
            "finite_count": self.finite_count,
            "mean": self.mean,
            "std": std,
            "min": self.minimum,
            "max": self.maximum,
        }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_train_only_normalization(
    dataset_root: str | Path,
    replay_root: str | Path,
    elevation_path: str | Path,
    output_path: str | Path,
    *,
    dataset_version: str,
    replay_version: str,
    git_sha: str,
) -> dict[str, Any]:
    """Fit final statistics only after genuine train artifacts exist; validation is never opened."""
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"Versioned normalization artifact already exists: {output}")

    dataset_root, replay_root = Path(dataset_root), Path(replay_root)
    dataset_manifest_path = dataset_root / "manifest.json"
    if not dataset_manifest_path.is_file():
        raise FileNotFoundError(f"Dataset manifest missing: {dataset_manifest_path}")
    manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))

    # Replay manifest verification
    replay_manifest_path = replay_root / "manifest.json"
    if not replay_manifest_path.is_file():
        raise FileNotFoundError(f"Replay manifest missing: {replay_manifest_path}")
    replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    if replay_manifest.get("execution_state") != "COMPLETE":
        raise ValueError("Replay execution is not marked COMPLETE in replay manifest")

    records = {
        entry["event_id"]: entry for entry in manifest["events"] if entry["split"] == "train"
    }
    if set(records) != set(TRAIN_EVENTS_AUTHORITATIVE):
        raise ValueError("Normalization requires exactly 12 authoritative train events")
    if any(is_locked_test_event(key) or key in VALIDATION_EVENTS_AUTHORITATIVE for key in records):
        raise PermissionError("Validation/test event entered normalization fit")

    # Static elevation verification
    elevation_path = Path(elevation_path)
    if not elevation_path.is_file():
        raise FileNotFoundError(f"Static elevation file not found: {elevation_path}")
    elevation = np.load(elevation_path, allow_pickle=False)
    if not np.isfinite(elevation).all():
        raise ValueError("Static elevation contains NaN or Inf")
    if elevation.shape not in ((256, 256), (1, 256, 256)):
        raise ValueError(f"Static elevation shape mismatch: {elevation.shape}")

    accumulators = {
        key: RunningStats() for key in (*OBSERVATION_CHANNELS, *NWP_CHANNELS, *STATIC_CHANNELS)
    }
    accumulators["static_elevation"].update(elevation)

    source_hashes = [
        _sha(dataset_manifest_path),
        _sha(replay_manifest_path),
        _sha(elevation_path),
    ]

    total_train_issues = 0

    for event_id, record in records.items():
        # Open GPM store (train only)
        gpm_path = dataset_root / record["path"]
        if not gpm_path.exists():
            raise FileNotFoundError(f"GPM store missing: {gpm_path}")
        store = zarr.open(str(gpm_path), mode="r")
        gpm_rainfall = store["rainfall"][:]
        if not np.isfinite(gpm_rainfall).all():
            raise ValueError(f"Non-finite values in GPM store for event {event_id}")
        if (gpm_rainfall < 0.0).any():
            raise ValueError(f"Negative rainfall in GPM store for event {event_id}")
        accumulators["rainfall_gpm"].update(gpm_rainfall)

        event_dir = replay_root / event_id
        if not event_dir.is_dir():
            raise FileNotFoundError(f"Event replay directory missing: {event_dir}")

        issue_dirs = sorted([d for d in event_dir.iterdir() if d.is_dir()])
        if len(issue_dirs) != 17:
            raise ValueError(
                f"Event {event_id} expected exactly 17 issues, found {len(issue_dirs)}"
            )
        total_train_issues += len(issue_dirs)

        for issue_dir in issue_dirs:
            metadata_path = issue_dir / "metadata.json"
            rain_path = issue_dir / "rainfall.npz"
            meteo_path = issue_dir / "meteorology.npz"

            if not metadata_path.is_file() or not rain_path.is_file() or not meteo_path.is_file():
                raise FileNotFoundError(f"Missing replay files in {issue_dir}")

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("event_id") != event_id or metadata.get("split") != "train":
                raise ValueError(
                    f"Replay split/event mismatch: {metadata.get('event_id')} split={metadata.get('split')}"
                )

            # Reject provisional / synthetic / placeholder tags
            source_prov = metadata.get("source_provenance") or {}
            if not source_prov:
                raise ValueError(f"Required source provenance absent in {metadata_path}")
            for prov_key, prov_val in source_prov.items():
                items = prov_val if isinstance(prov_val, list) else [prov_val]
                for item in items:
                    if isinstance(item, dict):
                        if item.get("placeholder", False) or item.get("provisional") or item.get("synthetic"):
                            raise ValueError(f"Provisional/placeholder provenance in {issue_dir}: {prov_key}")
                        if item.get("parser_state") not in (None, "PASSED"):
                            raise ValueError(f"Unsuccessful parser state in {issue_dir}: {prov_key}")

            with np.load(rain_path, allow_pickle=False) as rain:
                rain_arr = rain["rainfall_rate_mm_h"]
                if not np.isfinite(rain_arr).all():
                    raise ValueError(f"Non-finite rainfall in {rain_path}")
                if (rain_arr < 0.0).any():
                    raise ValueError(f"Negative rainfall in {rain_path}")
                accumulators["gfs_precipitation"].update(rain_arr)

            with np.load(meteo_path, allow_pickle=False) as meteo:
                for channel in NWP_CHANNELS[1:]:
                    if channel not in meteo:
                        raise ValueError(f"Required rich GFS channel absent in {meteo_path}: {channel}")
                    m_arr = meteo[channel]
                    if not np.isfinite(m_arr).all():
                        raise ValueError(f"Non-finite meteorology {channel} in {meteo_path}")
                    accumulators[channel].update(m_arr)

            source_hashes.extend(
                (
                    _sha(metadata_path),
                    _sha(rain_path),
                    _sha(meteo_path),
                )
            )

    if total_train_issues != 204:
        raise ValueError(
            f"Expected exactly 204 train issues across 12 train events, found {total_train_issues}"
        )

    grouped = {
        "obs_history": {key: accumulators[key].result() for key in OBSERVATION_CHANNELS},
        "nwp_future": {key: accumulators[key].result() for key in NWP_CHANNELS},
        "static_features": {key: accumulators[key].result() for key in STATIC_CHANNELS},
    }

    artifact = {
        "normalization_version": "phase4e_train_only_v1",
        "status": "PASS",
        "audit_passed": True,
        "fitted_split": "train",
        "fitted_event_ids": list(TRAIN_EVENTS_AUTHORITATIVE),
        "total_train_events": 12,
        "total_train_issues": total_train_issues,
        "dataset_version": dataset_version,
        "gfs_replay_version": replay_version,
        "git_sha": git_sha,
        "dataset_manifest_hash": _sha(dataset_manifest_path),
        "replay_manifest_hash": _sha(replay_manifest_path),
        "elevation_hash": _sha(elevation_path),
        "samples_count": {
            "train_events": 12,
            "train_issues": total_train_issues,
            "pixels_per_channel": {
                c: accumulators[c].count
                for c in (*OBSERVATION_CHANNELS, *NWP_CHANNELS, *STATIC_CHANNELS)
            },
        },
        "channel_order": {
            "obs_history": list(OBSERVATION_CHANNELS),
            "nwp_future": list(NWP_CHANNELS),
            "static_features": list(STATIC_CHANNELS),
        },
        "statistics": grouped,
        "source_hashes": sorted(set(source_hashes)),
        "fitted_at": datetime.now(UTC).isoformat(),
        "validation_opened": False,
        "locked_test_opened": False,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Versioned normalization artifact already exists: {output}")
    part = output.with_suffix(output.suffix + ".part")
    part.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(output)
    return artifact


def tournament_execution_plan() -> dict[str, Any]:
    return {
        "models": [
            "Persistence",
            "PySTEPS",
            "ConvLSTM V2",
            "ConvLSTM V3",
            "U-Net + ConvGRU",
            "ST Attention",
        ],
        "deep_training_seeds": [26071, 26072, 26073],
        "inputs": {
            "obs_history": [4, 1, 128, 128],
            "nwp_future": [4, 11, 128, 128],
            "static_features": [1, 128, 128],
        },
        "runtime_features": [
            "AMP",
            "Drive checkpointing",
            "resume",
            "early stopping",
            "best checkpoint",
            "OOM-safe batch fallback",
            "runtime logging",
            "peak GPU memory",
            "parameter count",
            "artifact hashes",
        ],
        "validation_metrics": [
            "MAE",
            "RMSE",
            "Bias",
            "CSI@0.1",
            "CSI@1",
            "CSI@5",
            "CSI@10_if_supported",
            "POD",
            "FAR",
            "F1",
        ],
        "confidence_intervals": "block_or_event_bootstrap_only",
        "ablations": {
            "A": ["GPM"],
            "B": ["GPM", "GFS precipitation"],
            "C": ["GPM", "full rich GFS"],
            "D": ["GPM", "full rich GFS", "elevation"],
        },
        "source_dropout": ["missing GFS precip", "missing ancillary GFS", "missing terrain"],
        "split": "validation_only",
        "locked_test_access": False,
        "execution_state": "NOT_STARTED",
    }


def freeze_winner(selection: dict[str, Any], prerequisites: dict[str, bool], output: str | Path):
    required = (
        "genuine_full_non_test_replay",
        "replay_audit",
        "real_channel_audit",
        "train_only_normalization",
        "multiseed_training",
        "validation_tournament",
        "required_ablations",
    )
    missing = [key for key in required if not prerequisites.get(key)]
    if missing:
        raise RuntimeError(f"Model freeze gate closed; missing: {missing}")
    required_fields = (
        "model_name",
        "architecture",
        "checkpoint",
        "checkpoint_sha256",
        "git_sha",
        "dataset_version",
        "gfs_replay_version",
        "normalization_sha256",
        "seed",
        "selection_metric",
        "validation_metrics",
        "config",
    )
    absent = [key for key in required_fields if key not in selection]
    if absent:
        raise ValueError(f"Winner manifest missing: {absent}")
    manifest = {
        **selection,
        "freeze_timestamp": datetime.now(UTC).isoformat(),
        "MODEL_SELECTION_FROZEN": True,
        "LOCKED_TEST_ALLOWED_FOR_SINGLE_FINAL_EVALUATION": True,
        "locked_test_automatically_run": False,
    }
    path = Path(output)
    if path.exists():
        raise FileExistsError("Winner manifest is immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
