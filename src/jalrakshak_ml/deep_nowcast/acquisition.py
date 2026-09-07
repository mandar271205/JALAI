"""Bounded, versioned historical GPM acquisition for Phase 3.

Each event is committed as an independent Zarr store. A temporary sibling is
fully written and validated before an atomic rename, so an interrupted event
does not corrupt already acquired training data.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import zarr

from jalrakshak_ml.adapters.gpm import GPMIMERGAdapter, granule_filename, iter_half_hour_times
from jalrakshak_ml.config import load_pilot_config, load_yaml
from jalrakshak_ml.preprocessing.grid import build_target_grid
from jalrakshak_ml.utils.hashing import sha256_file


def _parse_utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


@dataclass(frozen=True, slots=True)
class HistoricalEvent:
    event_id: str
    start: datetime
    end: datetime
    split: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> HistoricalEvent:
        split = str(value["split"]).lower()
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"Unsupported split {split!r}")
        event = cls(
            event_id=str(value["id"]),
            start=_parse_utc(value["start"]),
            end=_parse_utc(value["end"]),
            split=split,
        )
        if event.end <= event.start:
            raise ValueError(f"Event {event.event_id} has an invalid time range")
        times = list(iter_half_hour_times(event.start, event.end))
        if not times or times[0] != event.start or times[-1] + timedelta(minutes=30) != event.end:
            raise ValueError(f"Event {event.event_id} must align exactly to 30-minute boundaries")
        return event

    @property
    def expected_frames(self) -> int:
        return len(list(iter_half_hour_times(self.start, self.end)))

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "split": self.split,
            "expected_frames": self.expected_frames,
        }


def validate_events(events: Iterable[HistoricalEvent]) -> list[HistoricalEvent]:
    events = sorted(events, key=lambda item: (item.start, item.event_id))
    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("Historical event IDs must be unique")
    for left, right in pairwise(events):
        if right.start < left.end:
            raise ValueError(f"Historical events overlap: {left.event_id} and {right.event_id}")
    if {event.split for event in events} != {"train", "validation", "test"}:
        raise ValueError("At least one complete event is required in train, validation, and test")
    return events


class HistoricalDataAcquirer:
    """Acquire configured IMERG events without exceeding declared budgets."""

    def __init__(self, config_path: str | Path, adapter: GPMIMERGAdapter | None = None):
        self.config_path = Path(config_path).resolve()
        self.repo_root = self.config_path.parents[2]
        self.config = load_yaml(self.config_path)
        self.data_cfg = self.config["data"]
        self.acquisition_cfg = self.config["acquisition"]
        self.data_version = str(self.data_cfg["version"])
        self.output_root = self.repo_root / self.data_cfg["output_root"] / self.data_version
        self.events_dir = self.output_root / "events"
        self.raw_dir = self.repo_root / self.data_cfg["raw_dir"]
        self.events = validate_events(
            HistoricalEvent.from_mapping(item) for item in self.config["events"]
        )
        pilot = load_pilot_config(self.repo_root / self.data_cfg["pilot_config"])
        self.pilot = pilot
        self.target_grid = build_target_grid(
            bbox_wgs84=pilot["bbox_wgs84"],
            analysis_crs=pilot["analysis_crs"],
            width=pilot["grid"]["width"],
            height=pilot["grid"]["height"],
        )
        self.adapter = adapter or GPMIMERGAdapter(
            product_version=str(self.data_cfg.get("source_version", "07")).removeprefix("IMERG_V")
        )

    def plan(self) -> dict[str, Any]:
        total_frames = sum(event.expected_frames for event in self.events)
        max_frames = int(self.acquisition_cfg["max_frames"])
        if total_frames > max_frames:
            raise RuntimeError(f"Plan requests {total_frames} frames, exceeding max_frames={max_frames}")

        cached = 0
        for event in self.events:
            for valid_time in iter_half_hour_times(event.start, event.end):
                if (self.raw_dir / granule_filename(valid_time, self.adapter.product_version)).exists():
                    cached += 1
        new_files = total_frames - cached
        estimate_mb = float(self.acquisition_cfg["estimated_granule_mb"])
        estimated_download_gb = new_files * estimate_mb / 1024.0
        max_download_gb = float(self.acquisition_cfg["max_download_gb"])
        if estimated_download_gb > max_download_gb:
            raise RuntimeError(
                f"Estimated new download {estimated_download_gb:.3f} GiB exceeds "
                f"max_download_gb={max_download_gb:.3f}"
            )
        raw_existing_gb = _directory_bytes(self.raw_dir) / 1024**3
        max_total_raw_gb = float(self.acquisition_cfg["max_total_raw_gb"])
        if raw_existing_gb + estimated_download_gb > max_total_raw_gb:
            raise RuntimeError(
                f"Estimated total raw storage {raw_existing_gb + estimated_download_gb:.3f} GiB "
                f"exceeds max_total_raw_gb={max_total_raw_gb:.3f}"
            )
        return {
            "data_version": self.data_version,
            "events": [event.to_json() for event in self.events],
            "total_planned_frames": total_frames,
            "cached_raw_frames": cached,
            "estimated_new_files": new_files,
            "estimated_download_gb": round(estimated_download_gb, 4),
            "existing_raw_gb": round(raw_existing_gb, 4),
            "limits": {
                "max_frames": max_frames,
                "max_download_gb": max_download_gb,
                "max_total_raw_gb": max_total_raw_gb,
            },
        }

    def run(self, *, execute: bool = False) -> dict[str, Any]:
        """Return a plan by default; download only when ``execute=True``."""
        plan = self.plan()
        if not execute:
            return {"status": "DRY_RUN", **plan}
        self.events_dir.mkdir(parents=True, exist_ok=True)
        completed = []
        for event in self.events:
            completed.append(self._acquire_event(event))
            total_raw_gb = _directory_bytes(self.raw_dir) / 1024**3
            if total_raw_gb > float(self.acquisition_cfg["max_total_raw_gb"]):
                raise RuntimeError("Raw storage limit exceeded; acquisition stopped")
            self._write_version_manifest()
        audit = audit_training_dataset(self.output_root)
        _atomic_json(self.output_root / "audit.json", audit)
        return {"status": "COMPLETE", "plan": plan, "completed": completed, "audit": audit}

    def _acquire_event(self, event: HistoricalEvent) -> dict[str, Any]:
        final_path = self.events_dir / f"{event.event_id}.zarr"
        if final_path.exists():
            root = zarr.open(str(final_path), mode="r")
            if root.attrs.get("data_version") != self.data_version:
                raise RuntimeError(f"Existing event has wrong data_version: {final_path}")
            return {"event_id": event.event_id, "status": "EXISTS", "frames": int(root["time"].shape[0])}

        frames: list[np.ndarray] = []
        manifests = []
        for frame, manifest in self.adapter.fetch(
            bbox_wgs84=self.pilot["bbox_wgs84"],
            start_date=event.start,
            end_date=event.end,
            raw_dir=self.raw_dir,
            target_grid=self.target_grid,
            max_workers=int(self.acquisition_cfg.get("download_workers", 1)),
        ):
            frames.append(np.asarray(frame, dtype=np.float32))
            manifests.append(manifest)
        if not frames:
            raise RuntimeError(f"No frames acquired for {event.event_id}")

        times = [manifest.valid_time.astimezone(UTC).isoformat() for manifest in manifests]
        if len(times) != len(set(times)) or times != sorted(times):
            raise RuntimeError(f"Event {event.event_id} is not unique and monotonic")
        rainfall = np.stack(frames)
        valid_mask = np.isfinite(rainfall)
        # Zarr writes metadata via temporary sibling files. Stage outside the
        # OneDrive-synchronised tree to avoid sync-client locks, then atomically
        # move the completed directory onto the same local volume.
        temp_path = Path(tempfile.mkdtemp(prefix="jr_phase3_"))
        try:
            root = zarr.open(str(temp_path), mode="w")
            time_chunk = max(1, min(24, rainfall.shape[0]))
            chunks = (time_chunk, min(64, rainfall.shape[1]), min(64, rainfall.shape[2]))
            rain_arr = root.create_array("rainfall", shape=rainfall.shape, chunks=chunks, dtype="float32")
            rain_arr[:] = rainfall
            mask_arr = root.create_array("valid_mask", shape=valid_mask.shape, chunks=chunks, dtype="bool")
            mask_arr[:] = valid_mask
            time_arr = root.create_array("time", shape=(len(times),), chunks=(time_chunk,), dtype="str")
            time_arr[:] = np.asarray(times, dtype=str)
            quality = np.asarray([item.quality_score for item in manifests], dtype=np.float32)
            missing = np.asarray([item.missing_percent for item in manifests], dtype=np.float32)
            quality_arr = root.create_array("quality_score", shape=quality.shape, chunks=(time_chunk,), dtype="float32")
            quality_arr[:] = quality
            missing_arr = root.create_array("missing_percent", shape=missing.shape, chunks=(time_chunk,), dtype="float32")
            missing_arr[:] = missing

            raw_files = []
            for manifest in manifests:
                raw_path = self.raw_dir / granule_filename(manifest.valid_time, self.adapter.product_version)
                raw_files.append({
                    "path": raw_path.relative_to(self.repo_root).as_posix(),
                    "sha256": sha256_file(raw_path),
                    "bytes": raw_path.stat().st_size,
                })
            root.attrs.update({
                "event_id": event.event_id,
                "split": event.split,
                "start": event.start.isoformat(),
                "end": event.end.isoformat(),
                "expected_frames": event.expected_frames,
                "actual_frames": len(times),
                "temporal_step_minutes": 30,
                "data_version": self.data_version,
                "source": "NASA GPM IMERG Final Run Half-Hourly",
                "source_version": self.data_cfg.get("source_version", "IMERG_V07"),
                "source_resolution": manifests[0].source_resolution,
                "canonical_resolution": manifests[0].canonical_resolution,
                "units": "mm/h",
                "weather_frames": [item.model_dump(mode="json") for item in manifests],
                "raw_files": raw_files,
            })
            reopened = zarr.open(str(temp_path), mode="r")
            if reopened["rainfall"].shape != rainfall.shape or reopened["time"].shape[0] != len(times):
                raise RuntimeError("Temporary event store failed validation")
            del reopened, root, rain_arr, mask_arr, time_arr, quality_arr, missing_arr
            for attempt in range(5):
                try:
                    os.replace(temp_path, final_path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.25 * (attempt + 1))
        except Exception:
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)
            raise
        return {"event_id": event.event_id, "status": "CREATED", "frames": len(times)}

    def _write_version_manifest(self) -> None:
        records = []
        for path in sorted(self.events_dir.glob("*.zarr")):
            root = zarr.open(str(path), mode="r")
            records.append({
                "event_id": root.attrs["event_id"],
                "split": root.attrs["split"],
                "path": path.relative_to(self.output_root).as_posix(),
                "start": root.attrs["start"],
                "end": root.attrs["end"],
                "expected_frames": int(root.attrs["expected_frames"]),
                "actual_frames": int(root["time"].shape[0]),
            })
        _atomic_json(self.output_root / "manifest.json", {
            "data_version": self.data_version,
            "source": "NASA GPM IMERG Final Run Half-Hourly",
            "source_version": self.data_cfg.get("source_version", "IMERG_V07"),
            "temporal_step_minutes": 30,
            "created_or_updated_at": datetime.now(UTC).isoformat(),
            "events": records,
        })


def audit_training_dataset(version_dir: str | Path) -> dict[str, Any]:
    """Audit all committed event stores without treating gaps as valid sequences."""
    version_dir = Path(version_dir)
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    event_records = manifest["events"]
    total_pixels = valid_pixels = threshold_frames_den = 0
    rainfall_sum = rainfall_sq_sum = 0.0
    minimum, maximum = math.inf, -math.inf
    threshold_hits = {"0.1": 0, "1.0": 0, "5.0": 0}
    threshold_frames = {"0.1": 0, "1.0": 0, "5.0": 0}
    sampled_values: list[np.ndarray] = []
    actual_frames = expected_frames = 0
    raw_file_count = raw_bytes = 0
    dates: set[str] = set()
    event_summaries = []

    for record in event_records:
        root = zarr.open(str(version_dir / record["path"]), mode="r")
        rainfall = np.asarray(root["rainfall"][:], dtype=np.float32)
        mask = np.asarray(root["valid_mask"][:], dtype=bool) & np.isfinite(rainfall)
        times = [str(item) for item in root["time"][:]]
        values = rainfall[mask]
        total_pixels += rainfall.size
        valid_pixels += values.size
        actual_frames += rainfall.shape[0]
        expected_frames += int(root.attrs["expected_frames"])
        raw_files = root.attrs.get("raw_files", [])
        raw_file_count += len(raw_files)
        raw_bytes += sum(int(item.get("bytes", 0)) for item in raw_files)
        dates.update(item[:10] for item in times)
        threshold_frames_den += rainfall.shape[0]
        if values.size:
            rainfall_sum += float(values.sum(dtype=np.float64))
            rainfall_sq_sum += float(np.square(values, dtype=np.float64).sum(dtype=np.float64))
            minimum = min(minimum, float(values.min()))
            maximum = max(maximum, float(values.max()))
            stride = max(1, math.ceil(values.size / 250_000))
            sampled_values.append(values[::stride])
        for key in threshold_hits:
            threshold = float(key)
            threshold_hits[key] += int(np.sum(values >= threshold))
            threshold_frames[key] += int(np.sum(np.any((rainfall >= threshold) & mask, axis=(1, 2))))
        event_summaries.append({
            "event_id": record["event_id"],
            "split": record["split"],
            "start": times[0] if times else None,
            "end": times[-1] if times else None,
            "actual_frames": rainfall.shape[0],
            "expected_frames": int(root.attrs["expected_frames"]),
        })

    sample = np.concatenate(sampled_values) if sampled_values else np.asarray([], dtype=np.float32)
    mean = rainfall_sum / valid_pixels if valid_pixels else None
    variance = max(0.0, rainfall_sq_sum / valid_pixels - mean**2) if valid_pixels else None
    distribution = {
        "minimum_mm_h": minimum if valid_pixels else None,
        "mean_mm_h": mean,
        "standard_deviation_mm_h": math.sqrt(variance) if variance is not None else None,
        "p50_mm_h": float(np.percentile(sample, 50)) if sample.size else None,
        "p90_mm_h": float(np.percentile(sample, 90)) if sample.size else None,
        "p95_mm_h": float(np.percentile(sample, 95)) if sample.size else None,
        "p99_mm_h": float(np.percentile(sample, 99)) if sample.size else None,
        "maximum_mm_h": maximum if valid_pixels else None,
        "percentile_sample_size": int(sample.size),
    }
    source_resolution = None
    canonical_resolution = None
    if event_records:
        first = zarr.open(str(version_dir / event_records[0]["path"]), mode="r")
        source_resolution = first.attrs.get("source_resolution")
        canonical_resolution = first.attrs.get("canonical_resolution")
    return {
        "audit_time": datetime.now(UTC).isoformat(),
        "data_version": manifest["data_version"],
        "source": manifest["source"],
        "source_version": manifest["source_version"],
        "source_resolution": source_resolution,
        "canonical_resolution": canonical_resolution,
        "temporal_step_minutes": 30,
        "total_frames": actual_frames,
        "expected_frames": expected_frames,
        "temporal_missing_percentage": 100.0 * (expected_frames - actual_frames) / expected_frames if expected_frames else None,
        "total_events": len(event_records),
        "total_days": len(dates),
        "raw_file_count": raw_file_count,
        "raw_bytes": raw_bytes,
        "pixel_missing_percentage": 100.0 * (total_pixels - valid_pixels) / total_pixels if total_pixels else None,
        "rainfall_distribution": distribution,
        "threshold_event_frequencies": {
            key: {
                "pixel_fraction": threshold_hits[key] / valid_pixels if valid_pixels else None,
                "frames_with_event_fraction": threshold_frames[key] / threshold_frames_den if threshold_frames_den else None,
            }
            for key in threshold_hits
        },
        "events": event_summaries,
    }


def write_data_report(audit: dict[str, Any], output_path: str | Path) -> None:
    output_path = Path(output_path)
    events = "\n".join(
        f"- `{item['event_id']}` ({item['split']}): {item['actual_frames']}/{item['expected_frames']} frames, "
        f"{item['start']} to {item['end']}"
        for item in audit["events"]
    )
    dist = audit["rainfall_distribution"]
    threshold_rows = "\n".join(
        f"| {key} | {value['pixel_fraction']:.6f} | {value['frames_with_event_fraction']:.6f} |"
        for key, value in audit["threshold_event_frequencies"].items()
    )
    text = f"""# Phase 3 Training-Data Report

## Dataset

- Data version: `{audit['data_version']}`
- Source: {audit['source']} ({audit['source_version']})
- Native cadence: {audit['temporal_step_minutes']} minutes
- Source resolution: {audit['source_resolution']}
- Canonical resolution: {audit['canonical_resolution']}
- Events/days: {audit['total_events']} / {audit['total_days']}
- Frames: {audit['total_frames']} actual / {audit['expected_frames']} expected
- Preserved raw source files: {audit['raw_file_count']} ({audit['raw_bytes'] / 1024**3:.4f} GiB)
- Temporal missing: {audit['temporal_missing_percentage']:.4f}%
- Pixel missing: {audit['pixel_missing_percentage']:.4f}%

## Event-Isolated Splits

{events}

## Rainfall Distribution

- Minimum / mean / maximum: {dist['minimum_mm_h']:.4f} / {dist['mean_mm_h']:.4f} / {dist['maximum_mm_h']:.4f} mm/h
- P50 / P90 / P95 / P99: {dist['p50_mm_h']:.4f} / {dist['p90_mm_h']:.4f} / {dist['p95_mm_h']:.4f} / {dist['p99_mm_h']:.4f} mm/h
- Standard deviation: {dist['standard_deviation_mm_h']:.4f} mm/h
- Percentile sample size: {dist['percentile_sample_size']}

| Threshold (mm/h) | Valid-pixel fraction | Frames containing event |
|---:|---:|---:|
{threshold_rows}

All splits are whole events. Adjacent windows are never randomly divided across train, validation, and test.

## Limitation

This 72-frame, three-window corpus is sufficient to exercise the complete training pipeline and event-aware split logic, but it is still too small for a scientifically meaningful rainfall-nowcast validation. Expand the bounded event list deliberately before the real Colab GPU training campaign.
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
