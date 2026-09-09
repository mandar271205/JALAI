"""Read-only auditors for Phase 4E rich GFS acquisition and replay artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.deep_nowcast.splits import is_locked_test_event

from .core import utc
from .rich_download import (
    REQUIRED_FIELDS,
    default_message_validator,
    granule_directory,
    sha256_file,
    validate_grib_envelope,
)


def audit_download(plan: dict[str, Any], cache_root: str | Path) -> dict[str, Any]:
    pairs = plan["unique_cycle_leads_required"]
    if len(pairs) != 225:
        raise ValueError("Expected exactly 225 planned cycle+lead pairs")
    if any(is_locked_test_event(event_id) for event_id in plan["events"]):
        raise PermissionError("Locked-test mapping found")
    complete, incomplete, missing, failed, bytes_total = 0, 0, 0, 0, 0
    records, seen = [], set()
    for pair in pairs:
        key = (pair["cycle"], int(pair["lead"]))
        if key in seen:
            raise ValueError(f"Duplicate pair: {key}")
        seen.add(key)
        directory = granule_directory(cache_root, *key)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            missing += 1
            records.append({"cycle": key[0], "lead": key[1], "state": "MISSING"})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        variable_records, errors = {}, []
        for variable in REQUIRED_FIELDS:
            source = manifest.get("variables", {}).get(variable)
            if not source or source.get("completion_state") != "COMPLETE":
                errors.append(f"{variable}: incomplete")
                continue
            path = directory / source["path"]
            try:
                size = validate_grib_envelope(path, source["bytes_received"])
                if sha256_file(path) != source["sha256"]:
                    raise ValueError("SHA256 mismatch")
                parsed = default_message_validator(path, variable, utc(key[0]), key[1])
                bytes_total += size
                variable_records[variable] = {
                    "bytes": size,
                    "sha256": source["sha256"],
                    "finite_percentage": parsed["finite_percentage"],
                    "physical_min": parsed["physical_min"],
                    "physical_max": parsed["physical_max"],
                    "source_valid_time": parsed["source_valid_time"],
                    "precip_interval_metadata": parsed["precip_interval_metadata"],
                }
            except Exception as error:
                errors.append(f"{variable}: {type(error).__name__}: {error}")
        if errors:
            failed += 1
            incomplete += 1
            state = "INCOMPLETE"
        else:
            complete += 1
            state = "COMPLETE"
        records.append(
            {
                "cycle": key[0],
                "lead": key[1],
                "state": state,
                "variables": variable_records,
                "errors": errors,
            }
        )
    return {
        "audit_version": "phase4e_rich_gfs_download_audit_v1",
        "expected_pairs": 225,
        "complete_pairs": complete,
        "incomplete_pairs": incomplete,
        "missing_pairs": missing,
        "failed_pairs": failed,
        "total_measured_bytes": bytes_total,
        "duplicates": 0,
        "required_fields": list(REQUIRED_FIELDS),
        "locked_test_event_mappings": 0,
        "audit_passed": complete == 225 and not (incomplete or missing or failed),
        "pairs": records,
    }


def audit_replay(plan: dict[str, Any], replay_root: str | Path) -> dict[str, Any]:
    if plan["total_events"] != 15 or plan["train_issues"] != 204 or plan["validation_issues"] != 51:
        raise ValueError("Authoritative non-test plan counts changed")
    root, errors, checked = Path(replay_root), [], 0
    for event_id, event in plan["events"].items():
        if is_locked_test_event(event_id) or event["split"] not in ("train", "validation"):
            raise PermissionError("Locked/test split found in replay plan")
        for issue in event["issues"]:
            folder = root / event_id / utc(issue["issue_time"]).strftime("%Y%m%dT%H%MZ")
            if not folder.exists():
                errors.append(f"missing:{event_id}:{issue['issue_time']}")
                continue
            try:
                metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                if metadata["split"] != event["split"] or metadata["event_id"] != event_id:
                    raise ValueError("split/event mismatch")
                if (
                    metadata["native_cadence_minutes"] != 60
                    or metadata["output_cadence_minutes"] != 30
                ):
                    raise ValueError("false cadence")
                if (
                    metadata["availability_basis"]
                    != "assumed_cycle_plus_6h_required_bundle_not_observed_publication"
                ):
                    raise ValueError("availability basis mismatch")
                if utc(metadata["availability_time"]) > utc(metadata["issue_time"]):
                    raise ValueError("future-cycle availability leakage")
                temporal = metadata.get("temporal_metadata") or {}
                if not temporal.get("instantaneous") or not temporal.get("precipitation"):
                    raise ValueError("missing source/aligned temporal provenance")
                with np.load(folder / "rainfall.npz", allow_pickle=False) as rain:
                    assert rain["rainfall_rate_mm_h"].shape == (4, 256, 256)
                with np.load(folder / "meteorology.npz", allow_pickle=False) as weather:
                    if len(weather.files) != 10 or any(
                        weather[k].shape != (4, 256, 256) for k in weather.files
                    ):
                        raise ValueError("meteorology schema mismatch")
                checked += 1
            except Exception as error:
                errors.append(f"invalid:{event_id}:{issue['issue_time']}:{error}")
    return {
        "expected_events": 15,
        "expected_train_events": 12,
        "expected_validation_events": 3,
        "expected_test_events": 0,
        "expected_issues": 255,
        "complete_issues": checked,
        "missing_or_invalid": errors,
        "locked_test_accessed": False,
        "native_cadence_minutes": 60,
        "source_resolution_deg": 0.25,
        "audit_passed": checked == 255 and not errors,
    }


def audit_real_channels(
    plan: dict[str, Any],
    replay_root: str | Path,
    *,
    dataset_root: str | Path | None = None,
    elevation_path: str | Path | None = None,
) -> dict[str, Any]:
    base = audit_replay(plan, replay_root)
    replay_root = Path(replay_root)
    channels = [
        "rainfall_gpm",
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
        "static_elevation",
    ]
    populated = {key: base["audit_passed"] for key in channels}
    populated["rainfall_gpm"] = bool(
        dataset_root and (Path(dataset_root) / "manifest.json").is_file()
    )
    populated["static_elevation"] = bool(elevation_path and Path(elevation_path).is_file())
    for event_id, event in plan["events"].items():
        for issue in event["issues"]:
            folder = replay_root / event_id / utc(issue["issue_time"]).strftime("%Y%m%dT%H%MZ")
            if not folder.exists():
                continue
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            provenance = metadata.get("source_provenance") or {}
            masks = metadata.get("availability_masks") or {}
            for channel in channels[1:-1]:
                records = provenance.get(channel)
                records = records if isinstance(records, list) else [records]
                valid_records = []
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    source = Path(record.get("source_path", ""))
                    if not source.is_absolute():
                        source = replay_root / source
                    valid_records.append(
                        source.is_file()
                        and record.get("parser_state") == "PASSED"
                        and record.get("placeholder", False) is False
                        and record.get("sha256") == sha256_file(source)
                    )
                mask_available = bool(np.asarray(masks.get(channel, False), dtype=bool).all())
                populated[channel] &= bool(valid_records and all(valid_records) and mask_available)
    return {
        "conceptual_input_count": 13,
        "channels": {
            key: {
                "CHANNEL_BINDING_IMPLEMENTED": True,
                "REAL_CHANNEL_POPULATED": populated[key],
            }
            for key in channels
        },
        "radar": {"CHANNEL_BINDING_IMPLEMENTED": True, "REAL_CHANNEL_POPULATED": False},
        "insat": {"CHANNEL_BINDING_IMPLEMENTED": True, "REAL_CHANNEL_POPULATED": False},
        "synthetic_substitution_used": False,
        "audit_passed": all(populated.values()),
    }
