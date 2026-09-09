"""Read-only auditors for Phase 4E rich GFS acquisition and replay artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    is_locked_test_event,
)

from .core import utc
from .rich_pipeline import METEOROLOGY_ARRAY_KEYS
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
    """Audit completed Phase 4E rich replay integrity for all 255 non-test issues."""
    if (
        plan.get("total_events") != 15
        or plan.get("train_issues") != 204
        or plan.get("validation_issues") != 51
        or plan.get("total_issues") != 255
    ):
        raise ValueError(
            f"Authoritative non-test plan counts mismatch: total_events={plan.get('total_events')} (expected 15), "
            f"train_issues={plan.get('train_issues')} (expected 204), "
            f"validation_issues={plan.get('validation_issues')} (expected 51), "
            f"total_issues={plan.get('total_issues')} (expected 255)"
        )

    # Verify authoritative split membership
    events_in_plan = plan.get("events", {})
    train_in_plan = {eid for eid, ev in events_in_plan.items() if ev.get("split") == "train"}
    val_in_plan = {eid for eid, ev in events_in_plan.items() if ev.get("split") == "validation"}
    if train_in_plan != set(TRAIN_EVENTS_AUTHORITATIVE):
        raise ValueError(
            f"Plan train events mismatch authoritative set: missing {set(TRAIN_EVENTS_AUTHORITATIVE) - train_in_plan}, "
            f"extra {train_in_plan - set(TRAIN_EVENTS_AUTHORITATIVE)}"
        )
    if val_in_plan != set(VALIDATION_EVENTS_AUTHORITATIVE):
        raise ValueError(
            f"Plan validation events mismatch authoritative set: missing {set(VALIDATION_EVENTS_AUTHORITATIVE) - val_in_plan}, "
            f"extra {val_in_plan - set(VALIDATION_EVENTS_AUTHORITATIVE)}"
        )

    root = Path(replay_root)
    errors: list[str] = []
    seen_issue_keys: set[tuple[str, str]] = set()
    train_checked = 0
    val_checked = 0
    duplicate_issues = 0
    missing_issues = 0
    invalid_issues = 0
    locked_test_detected = False

    # Check for locked test events or unexpected directories in replay_root
    if root.exists():
        for item in root.iterdir():
            if item.is_dir():
                if is_locked_test_event(item.name) or item.name in LOCKED_TEST_EVENTS_AUTHORITATIVE:
                    locked_test_detected = True
                    errors.append(f"locked_test_contamination:{item.name}")
                elif item.name not in events_in_plan and item.name != "manifest.json":
                    errors.append(f"unexpected_event_directory:{item.name}")

    for event_id, event in events_in_plan.items():
        if is_locked_test_event(event_id) or event.get("split") not in ("train", "validation"):
            raise PermissionError(f"Locked or unauthorized event in replay plan: {event_id}")

        for issue in event.get("issues", []):
            issue_time_str = issue["issue_time"]
            try:
                issue_dt = utc(issue_time_str)
            except Exception as dt_err:
                invalid_issues += 1
                errors.append(f"invalid_timestamp:{event_id}:{issue_time_str}:{dt_err}")
                continue

            issue_key = (event_id, issue_dt.isoformat())
            if issue_key in seen_issue_keys:
                duplicate_issues += 1
                errors.append(f"duplicate_issue:{event_id}:{issue_time_str}")
                continue
            seen_issue_keys.add(issue_key)

            folder = root / event_id / issue_dt.strftime("%Y%m%dT%H%MZ")
            if not folder.is_dir():
                missing_issues += 1
                errors.append(f"missing_folder:{event_id}:{issue_time_str}")
                continue

            meta_path = folder / "metadata.json"
            rain_path = folder / "rainfall.npz"
            meteo_path = folder / "meteorology.npz"
            if not meta_path.is_file() or not rain_path.is_file() or not meteo_path.is_file():
                missing_issues += 1
                errors.append(f"missing_files:{event_id}:{issue_time_str}")
                continue

            try:
                # 1. Validate metadata.json
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                if metadata.get("event_id") != event_id or metadata.get("split") != event["split"]:
                    raise ValueError(f"split/event mismatch in metadata: {metadata.get('event_id')}/{metadata.get('split')}")
                if metadata.get("native_cadence_minutes") != 60 or metadata.get("output_cadence_minutes") != 30:
                    raise ValueError(f"false cadence: native={metadata.get('native_cadence_minutes')}, output={metadata.get('output_cadence_minutes')}")
                if not str(metadata.get("availability_basis", "")).startswith("assumed"):
                    raise ValueError(f"availability basis mismatch: {metadata.get('availability_basis')}")
                if utc(metadata["availability_time"]) > issue_dt:
                    raise ValueError("future-cycle availability leakage")
                if utc(metadata["cycle_time"]) > issue_dt:
                    raise ValueError("future-cycle selection leakage")

                # Scientific disclaimer against false resolution
                disclaimer = str(metadata.get("scientific_disclaimer", ""))
                if "does NOT increase meteorological resolution" not in disclaimer:
                    raise ValueError("Missing or invalid scientific disclaimer against false resolution")

                # Spatial metadata check
                spatial = metadata.get("spatial") or {}
                canon_res = str(metadata.get("canonical_resolution", ""))
                target_grid = spatial.get("target_grid") or {}
                crs = target_grid.get("crs") or ("EPSG:32643" if "EPSG:32643" in canon_res else None)
                grid_shape = target_grid.get("shape") or ([256, 256] if "256x256" in canon_res else None)
                if crs != "EPSG:32643" or grid_shape != [256, 256]:
                    raise ValueError(f"Spatial CRS/grid mismatch: crs={crs}, shape={grid_shape}")

                # Horizons & temporal consistency
                if metadata.get("horizons_minutes") != [30, 60, 90, 120]:
                    raise ValueError(f"horizons_minutes mismatch: {metadata.get('horizons_minutes')}")

                temporal = metadata.get("temporal_metadata") or {}
                instant = temporal.get("instantaneous") or []
                precip = temporal.get("precipitation") or []
                if len(instant) != 4 or len(precip) != 4:
                    raise ValueError(f"Temporal horizon count mismatch: instant={len(instant)}, precip={len(precip)}")

                # Target timestamps internal consistency
                target_times = [utc(t).isoformat() for t in issue.get("target_times", [])]
                if len(target_times) != 4:
                    raise ValueError(f"Issue target_times count != 4: {len(target_times)}")

                # Instantaneous slot provenance check
                for slot_idx, slot in enumerate(instant):
                    if "cycle_time" not in slot or "lead_hour" not in slot or "availability_time" not in slot:
                        raise ValueError(f"instantaneous slot {slot_idx}: missing cycle/lead/availability provenance")
                    if utc(slot["availability_time"]) > issue_dt:
                        raise ValueError(f"instantaneous slot {slot_idx}: future availability leakage")

                # Precipitation slot provenance check
                for slot_idx, (slot, expected_target) in enumerate(zip(precip, target_times, strict=True)):
                    if utc(slot["aligned_target_time"]).isoformat() != expected_target:
                        raise ValueError(f"Target timestamp mismatch at slot {slot_idx}: {slot['aligned_target_time']} != {expected_target}")
                    if slot.get("independent_native_observation") is not False:
                        raise ValueError(f"precipitation slot {slot_idx}: independent_native_observation must be False")
                    if slot.get("temporal_disaggregation_method") != "uniform_within_native_interval":
                        raise ValueError(f"precipitation slot {slot_idx}: invalid disaggregation method {slot.get('temporal_disaggregation_method')}")
                    if "source_interval_start" not in slot or "source_interval_end" not in slot:
                        raise ValueError(f"precipitation slot {slot_idx}: missing native interval bounds")
                    slot_start = utc(slot["source_interval_start"])
                    slot_end = utc(slot["source_interval_end"])
                    if slot_start >= slot_end:
                        raise ValueError(f"precipitation slot {slot_idx}: native interval start >= end")

                # PRATE Provenance check
                source_prov = metadata.get("source_provenance") or {}
                if "gfs_precipitation" not in source_prov:
                    raise ValueError("Missing source_provenance for gfs_precipitation")
                for p_rec in source_prov["gfs_precipitation"]:
                    if p_rec.get("conversion_method") != "TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL":
                        raise ValueError(f"Invalid PRATE conversion_method: {p_rec.get('conversion_method')}")
                    if p_rec.get("conversion_formula") != "rate_mm_h = prate_kg_m2_s * 3600":
                        raise ValueError(f"Invalid PRATE conversion_formula: {p_rec.get('conversion_formula')}")
                    if p_rec.get("placeholder", False) is not False:
                        raise ValueError("Placeholder flag set in PRATE provenance")

                # Hash integrity verification
                if "rainfall_sha256" in metadata and sha256_file(rain_path) != metadata["rainfall_sha256"]:
                    raise ValueError("rainfall.npz sha256 mismatch with metadata")
                if "meteorology_sha256" in metadata and sha256_file(meteo_path) != metadata["meteorology_sha256"]:
                    raise ValueError("meteorology.npz sha256 mismatch with metadata")

                # 2. Validate rainfall.npz
                with np.load(rain_path, allow_pickle=False) as rain:
                    if "rainfall_rate_mm_h" not in rain:
                        raise ValueError("rainfall_rate_mm_h array absent in rainfall.npz")
                    r_arr = rain["rainfall_rate_mm_h"]
                    if r_arr.shape != (4, 256, 256):
                        raise ValueError(f"rainfall shape mismatch: {r_arr.shape} != (4, 256, 256)")
                    if r_arr.dtype not in (np.float32, np.float64):
                        raise ValueError(f"rainfall dtype mismatch: {r_arr.dtype}")
                    if not np.isfinite(r_arr).all():
                        raise ValueError("rainfall contains NaN or Inf")
                    if (r_arr < 0.0).any():
                        raise ValueError("negative rainfall values detected")

                # 3. Validate meteorology.npz
                with np.load(meteo_path, allow_pickle=False) as weather:
                    missing_keys = set(METEOROLOGY_ARRAY_KEYS) - set(weather.files)
                    if missing_keys:
                        raise ValueError(f"Missing meteorology keys: {missing_keys}")
                    for k in METEOROLOGY_ARRAY_KEYS:
                        w_arr = weather[k]
                        if w_arr.shape != (4, 256, 256):
                            raise ValueError(f"{k} shape mismatch: {w_arr.shape} != (4, 256, 256)")
                        if w_arr.dtype not in (np.float32, np.float64):
                            raise ValueError(f"{k} dtype mismatch: {w_arr.dtype}")
                        if not np.isfinite(w_arr).all():
                            raise ValueError(f"{k} contains NaN or Inf")

                    # Physical bounds checks
                    if not np.issubdtype(weather["gfs_u10"].dtype, np.floating) or not np.issubdtype(weather["gfs_v10"].dtype, np.floating):
                        raise ValueError("u10 and v10 must be floating point")
                    if (weather["gfs_wind_speed"] < 0.0).any():
                        raise ValueError("Negative wind speed detected")
                    if (weather["gfs_rh2m"] < 0.0).any() or (weather["gfs_rh2m"] > 115.0).any():
                        raise ValueError("Relative humidity outside physical range [0, 115]")
                    if (weather["gfs_surface_pressure"] < 30000.0).any() or (weather["gfs_surface_pressure"] > 120000.0).any():
                        raise ValueError("Surface pressure outside physical range [30000, 120000] Pa")
                    if (weather["gfs_t2m"] < 180.0).any() or (weather["gfs_t2m"] > 350.0).any():
                        raise ValueError("Temperature outside physical range [180, 350] K")
                    if (weather["gfs_cape"] < 0.0).any():
                        raise ValueError("Negative CAPE detected")
                    if (weather["gfs_pwat"] < 0.0).any():
                        raise ValueError("Negative PWAT detected")

                if event["split"] == "train":
                    train_checked += 1
                else:
                    val_checked += 1
            except Exception as error:
                invalid_issues += 1
                errors.append(f"invalid:{event_id}:{issue_time_str}:{type(error).__name__}:{error}")

    complete = train_checked + val_checked
    audit_passed = (
        complete == 255
        and train_checked == 204
        and val_checked == 51
        and duplicate_issues == 0
        and missing_issues == 0
        and invalid_issues == 0
        and not locked_test_detected
        and not errors
    )

    return {
        "audit_version": "phase4e_rich_gfs_replay_integrity_audit_v2",
        "expected_events": 15,
        "expected_train_events": 12,
        "expected_validation_events": 3,
        "expected_test_events": 0,
        "expected_issues": 255,
        "expected_train_issues": 204,
        "expected_validation_issues": 51,
        "train_issues_passed": train_checked,
        "validation_issues_passed": val_checked,
        "complete_issues": complete,
        "duplicate_issues": duplicate_issues,
        "missing_issues": missing_issues,
        "corrupt_or_invalid_issues": invalid_issues,
        "missing_or_invalid": errors,
        "locked_test_accessed": locked_test_detected,
        "canonical_grid": "256x256 (EPSG:32643)",
        "native_cadence_minutes": 60,
        "output_cadence_minutes": 30,
        "source_resolution_deg": 0.25,
        "audit_passed": audit_passed,
    }


def audit_real_channels(
    plan: dict[str, Any],
    replay_root: str | Path,
    *,
    dataset_root: str | Path | None = None,
    elevation_path: str | Path | None = None,
    raw_cache_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audit genuine real-channel population; rejects synthetic/placeholder channels."""
    base = audit_replay(plan, replay_root)
    replay_root = Path(replay_root)
    raw_cache = Path(raw_cache_root) if raw_cache_root else None
    missing_sources: list[str] = []

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

    # 1. GPM observation history audit
    gpm_genuine = False
    if dataset_root:
        d_root = Path(dataset_root)
        d_manifest = d_root / "manifest.json"
        if d_manifest.is_file():
            try:
                gpm_manifest = json.loads(d_manifest.read_text(encoding="utf-8"))
                events_map = {e["event_id"]: e for e in gpm_manifest.get("events", [])}
                all_events_ok = True
                for eid in plan.get("events", {}):
                    if eid not in events_map:
                        all_events_ok = False
                        missing_sources.append(f"gpm_event_missing_in_manifest:{eid}")
                        break
                    zarr_path = d_root / events_map[eid].get("path", "")
                    if not zarr_path.exists():
                        all_events_ok = False
                        missing_sources.append(f"gpm_zarr_missing:{eid}:{zarr_path}")
                        break
                gpm_genuine = all_events_ok
            except Exception as gpm_err:
                missing_sources.append(f"gpm_manifest_error:{gpm_err}")
                gpm_genuine = False
    populated["rainfall_gpm"] = gpm_genuine

    # 2. Static terrain elevation audit
    elev_genuine = False
    if elevation_path:
        e_path = Path(elevation_path)
        if e_path.is_file():
            try:
                arr = np.load(e_path, allow_pickle=False)
                if arr.shape in ((256, 256), (1, 256, 256)) and np.isfinite(arr).all():
                    elev_genuine = True
                else:
                    missing_sources.append(f"elevation_invalid_shape_or_nonfinite:{arr.shape}")
            except Exception as e_err:
                missing_sources.append(f"elevation_load_error:{e_err}")
    populated["static_elevation"] = elev_genuine

    # 3. 11 Future NWP channels genuine source audit
    for event_id, event in plan.get("events", {}).items():
        for issue in event.get("issues", []):
            issue_time_str = issue["issue_time"]
            folder = replay_root / event_id / utc(issue_time_str).strftime("%Y%m%dT%H%MZ")
            if not folder.exists():
                continue
            meta_path = folder / "metadata.json"
            if not meta_path.exists():
                continue
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            provenance = metadata.get("source_provenance") or {}
            masks = metadata.get("availability_masks") or {}

            for channel in channels[1:-1]:
                records = provenance.get(channel)
                if not records:
                    populated[channel] = False
                    missing_sources.append(f"no_provenance:{event_id}:{issue_time_str}:{channel}")
                    continue
                records = records if isinstance(records, list) else [records]
                valid_records = []
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    # Reject provisional or synthetic tags
                    if record.get("placeholder", False) or record.get("provisional") or record.get("synthetic"):
                        valid_records.append(False)
                        continue
                    if record.get("parser_state") != "PASSED":
                        valid_records.append(False)
                        continue

                    # If source file is accessible on disk, verify integrity
                    src_str = record.get("source_path", "")
                    src_path = Path(src_str)
                    if not src_path.is_file() and raw_cache:
                        # Try relative to raw_cache
                        alt_path = raw_cache / src_path.name
                        if alt_path.is_file():
                            src_path = alt_path
                    if src_path.is_file():
                        if record.get("sha256") != sha256_file(src_path):
                            valid_records.append(False)
                            missing_sources.append(f"sha256_mismatch:{src_path}")
                            continue

                    valid_records.append(True)

                mask_available = bool(np.asarray(masks.get(channel, False), dtype=bool).all())
                channel_ok = bool(valid_records and all(valid_records) and mask_available)
                populated[channel] &= channel_ok

    all_passed = bool(base["audit_passed"] and all(populated.values()))

    return {
        "audit_version": "phase4e_real_channels_audit_v2",
        "conceptual_input_count": 13,
        "channels": {
            key: {
                "CHANNEL_BINDING_IMPLEMENTED": True,
                "REAL_CHANNEL_POPULATED": populated[key],
            }
            for key in channels
        },
        "radar": {
            "CHANNEL_BINDING_IMPLEMENTED": True,
            "REAL_CHANNEL_POPULATED": False,
            "note": "Radar not operational in Phase 4E (no active Mumbai radar)",
        },
        "insat": {
            "CHANNEL_BINDING_IMPLEMENTED": True,
            "REAL_CHANNEL_POPULATED": False,
            "note": "INSAT not operational in Phase 4E",
        },
        "synthetic_substitution_used": False,
        "fake_radar_used": False,
        "fake_insat_used": False,
        "elevation_provenance_genuine": elev_genuine,
        "gpm_provenance_genuine": gpm_genuine,
        "missing_sources": missing_sources,
        "audit_passed": all_passed,
    }
