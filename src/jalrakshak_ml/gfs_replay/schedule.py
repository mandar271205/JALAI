"""Materialize the locked benchmark schedule using the existing sequence indexer."""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import zarr

from .core import ALL_SUPPORTED_EVENTS, LOCKED_EVENTS, NON_TEST_EVENTS, utc


def validate_events(events, purpose="held_out_replay_only"):
    identifiers = [event["event_id"] for event in events]
    if purpose == "held_out_replay_only":
        if len(identifiers) != 3 or set(identifiers) != set(LOCKED_EVENTS):
            raise ValueError("Exactly the three locked test events are required")
        if any(event["split"] != "test" for event in events):
            raise ValueError("Locked events cannot be used for training/calibration")
    elif purpose == "non_test_replay":
        if not identifiers or not set(identifiers).issubset(set(NON_TEST_EVENTS)):
            raise ValueError(f"Events must be a subset of NON_TEST_EVENTS: {NON_TEST_EVENTS}")
        if any(event["split"] not in ("train", "validation") for event in events):
            raise ValueError("Non-test replay events must have split 'train' or 'validation'")
    else:
        raise ValueError(f"Unknown replay purpose: {purpose}")


def materialize_schedule(config, repo_root):
    from jalrakshak_ml.deep_nowcast.dataset import RainfallSequenceDataset

    purpose = config.get("purpose", "held_out_replay_only")
    validate_events(config["events"], purpose=purpose)
    if (
        config["history_length"],
        config["prediction_horizon"],
        config["temporal_step_minutes"],
    ) != (4, 4, 30):
        raise ValueError("Locked sequence semantics changed")
    version = Path(repo_root) / config["preferred_dataset_dir"]
    saved_manifest = version / "manifest.json"
    saved = (
        json.loads(saved_manifest.read_text(encoding="utf-8")) if saved_manifest.exists() else None
    )

    # Only timestamps are needed by the unchanged dataset indexing method. No
    # rainfall arrays or synthetic benchmark observations are created here.
    class TimestampIndexer:
        input_channels = ("rainfall",)
        history_length = 4
        prediction_horizon = 4
        temporal_step_minutes = 30
        _index_event = RainfallSequenceDataset._index_event

        def __init__(self, times):
            self.times, self.indices = times, []

        def _open(self, path):
            return {"time": np.asarray(self.times), "rainfall": None}

    events = []
    for event in config["events"]:
        start, end = utc(event["start"]), utc(event["end"])
        if end - start != timedelta(hours=12):
            raise ValueError("Locked event must contain exactly 24 half-hour frames")
        times = [(start + timedelta(minutes=30 * i)).isoformat() for i in range(24)]
        source = config["definitions_provenance"]
        if saved is not None:
            records = [e for e in saved["events"] if e["event_id"] == event["event_id"]]
            if len(records) != 1 or records[0]["split"] != event["split"]:
                raise ValueError("Saved benchmark event missing or reassigned")
            store = zarr.open(str(version / records[0]["path"]), mode="r")
            actual = [utc(str(t)).isoformat() for t in store["time"][:]]
            if actual != times:
                raise ValueError("Saved timestamps disagree with locked event definition")
            times, source = actual, str(saved_manifest)
        indexer = TimestampIndexer(times)
        indexer._index_event({"event_id": event["event_id"], "path": "timestamp_metadata_only"})
        samples = [
            {
                "sample_index": i,
                "issue_time": index.input_times[-1],
                "input_times": list(index.input_times),
                "target_times": list(index.target_times),
            }
            for i, index in enumerate(indexer.indices)
        ]
        if len(samples) != config["expected_samples_per_event"]:
            raise ValueError("Benchmark sample count changed")
        events.append({**event, "timestamp_source": source, "samples": samples})
    total = sum(len(event["samples"]) for event in events)
    if total != config["expected_total_samples"]:
        raise ValueError("Sample count mismatch with expected_total_samples")
    if purpose == "held_out_replay_only" and total != 51:
        raise ValueError("Locked benchmark must contain 51 samples")
    method_source = inspect.getsource(RainfallSequenceDataset._index_event)
    benchmark_ver = config.get("benchmark_version", "mumbai_locked_test_51_v1" if purpose == "held_out_replay_only" else "mumbai_non_test_schedule_34_v1")
    manifest = {
        "benchmark_version": benchmark_ver,
        "purpose": purpose,
        "history_length": 4,
        "prediction_horizon": 4,
        "temporal_step_minutes": 30,
        "sequence_indexer": "RainfallSequenceDataset._index_event",
        "sequence_indexer_sha256": hashlib.sha256(method_source.encode()).hexdigest(),
        "expanded_dataset_mounted": saved is not None,
        "total_samples": total,
        "events": events,
    }
    path = Path(repo_root) / config["benchmark_manifest"]
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != manifest:
            raise ValueError(
                "Versioned benchmark manifest differs; review before creating a new version"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest, path
