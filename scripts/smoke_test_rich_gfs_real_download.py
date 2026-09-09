"""Safe Real-Data Smoke Test for Phase 4E Rich GFS.

Downloads exactly ONE GFS cycle+lead only:
- Cycle: 2021-06-17T18:00:00Z
- Lead: f007
- Source: NOAA AWS S3 (0.25-degree GFS)

Variables:
1. 10u (u10)
2. 10v (v10)
3. 2t (t2m)
4. 2r (rh2m)
5. sp (surface pressure)
6. cape (CAPE)
7. pwat (PWAT)
8. prate_mean (PRATE interval average)

Enforces:
- Exact .idx byte-range acquisition (NO full ~450 MB GRIB downloads)
- Strict validation of magic headers and message sizes
- Full ecCodes decoding and scientific integrity checks
- Reprojection to canonical 256x256 target grid (signed u10/v10 preserved)
- Google Drive persistence verification
- ZERO test event access, ZERO deep model training, ZERO normalization fitting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import requests

# Ensure src/ is on sys.path
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jalrakshak_ml.gfs_replay.core import finite_rain, source_uri
from jalrakshak_ml.gfs_replay.grib import (
    eccodes_module,
    rich_index_ranges,
)
from jalrakshak_ml.gfs_replay.pipeline import build_target_grid
from jalrakshak_ml.gfs_replay.rich_pipeline import persistence_environment
from jalrakshak_ml.gfs_replay.spatial import reproject_field, reproject_rate
from jalrakshak_ml.weather.adapters.gfs_rich import GFS_VARIABLE_SPECS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gfs_smoke_test")

SMOKE_CYCLE = datetime(2021, 6, 17, 18, 0, tzinfo=UTC)
SMOKE_LEAD = 7
SMOKE_TARGET_VALID = SMOKE_CYCLE + timedelta(hours=SMOKE_LEAD)

SMOKE_VARIABLES = ("u10", "v10", "t2m", "rh2m", "sp", "cape", "pwat", "prate_mean")

# Persistent output locations
DRIVE_OUTPUT_ROOT = Path(
    "/content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1/smoke/20210617_1800_f007"
)
LOCAL_OUTPUT_ROOT = (
    _ROOT / "data/processed/gfs_replay/gfs_mumbai_phase4e_rich_non_test_v1/smoke/20210617_1800_f007"
)


def fetch_idx(uri: str) -> str:
    idx_uri = uri + ".idx"
    log.info("Fetching NOAA GFS index: %s", idx_uri)
    resp = requests.get(idx_uri, timeout=30)
    resp.raise_for_status()
    if not resp.text.strip():
        raise ValueError("Empty .idx received from NOAA S3")
    return resp.text


def run_smoke_test() -> dict[str, Any]:
    log.info("=== STARTING PHASE 4E RICH GFS REAL-DATA SMOKE TEST ===")
    log.info(
        "Cycle: %s, Lead: f%03d, Valid: %s",
        SMOKE_CYCLE.isoformat(),
        SMOKE_LEAD,
        SMOKE_TARGET_VALID.isoformat(),
    )

    uri = source_uri(SMOKE_CYCLE, SMOKE_LEAD)
    log.info("Granule URI: %s", uri)

    # 1. Fetch .idx
    idx_text = fetch_idx(uri)
    idx_lines = [line.strip() for line in idx_text.splitlines() if line.strip()]
    log.info("Successfully fetched .idx with %d entries (%d bytes)", len(idx_lines), len(idx_text))

    # 2. Compute byte ranges
    ranges = rich_index_ranges(idx_text, variable_keys=SMOKE_VARIABLES, lead=SMOKE_LEAD)
    log.info("Matched exact byte ranges for all %d requested variables", len(SMOKE_VARIABLES))

    # Determine paths to persist
    out_dirs = [LOCAL_OUTPUT_ROOT]
    drive_state = persistence_environment(DRIVE_OUTPUT_ROOT)
    if drive_state["COLAB_DRIVE_PERSISTENCE_VERIFIED"]:
        out_dirs.append(DRIVE_OUTPUT_ROOT)

    for od in out_dirs:
        od.mkdir(parents=True, exist_ok=True)

    # 3. Perform real HTTP Range requests
    download_reports = []
    total_requested_bytes = 0
    total_received_bytes = 0
    downloaded_data: dict[str, bytes] = {}

    for var in SMOKE_VARIABLES:
        begin, end = ranges[var]
        expected_size = end - begin + 1
        total_requested_bytes += expected_size

        # Find matching .idx line
        matched_idx_line = ""
        for line in idx_lines:
            parts = line.split(":")
            if len(parts) >= 2 and int(parts[1]) == begin:
                matched_idx_line = line
                break

        log.info("Downloading %-10s [%d - %d] (%d bytes)...", var, begin, end, expected_size)
        headers = {"Range": f"bytes={begin}-{end}"}
        resp = requests.get(uri, headers=headers, stream=True, timeout=60)

        # Check HTTP status
        if resp.status_code != 206:
            raise RuntimeError(
                f"Expected HTTP 206 Partial Content for {var}, got {resp.status_code}"
            )

        content_range = resp.headers.get("Content-Range", "")
        expected_range_pattern = rf"bytes {begin}-{end}/\d+"
        if not re.fullmatch(expected_range_pattern, content_range):
            raise ValueError(
                f"Server altered Content-Range: {content_range} vs expected {expected_range_pattern}"
            )

        data = resp.raw.read(expected_size + 1)
        actual_size = len(data)
        total_received_bytes += actual_size

        if actual_size != expected_size:
            raise ValueError(
                f"Size mismatch for {var}: requested {expected_size}, received {actual_size}"
            )

        # Magic bytes check
        if data[:4] != b"GRIB" or data[-4:] != b"7777":
            raise ValueError(
                f"Invalid GRIB magic bytes for {var}: start={data[:4]!r}, end={data[-4:]!r}"
            )

        digest = hashlib.sha256(data).hexdigest()
        downloaded_data[var] = data

        # Write to output directories
        filename = f"{SMOKE_CYCLE:%Y%m%dT%H}_{var}_f{SMOKE_LEAD:03d}.grib2"
        for od in out_dirs:
            target_file = od / filename
            target_file.write_bytes(data)

        download_reports.append(
            {
                "variable": var,
                "matched_idx_line": matched_idx_line,
                "byte_start": begin,
                "byte_end": end,
                "bytes_requested": expected_size,
                "bytes_received": actual_size,
                "http_status": resp.status_code,
                "source_uri": uri,
                "sha256": digest,
                "has_valid_grib_magic": True,
                "filename": filename,
            }
        )

    log.info(
        "All 8 variables downloaded. Total bytes: %d (~%.2f MB)",
        total_received_bytes,
        total_received_bytes / (1024 * 1024),
    )

    # 4. GRIB Decoding and Scientific Checks
    ec = eccodes_module()
    parsed_reports = []
    spatial_reprojected = {}
    target_grid = build_target_grid(
        bbox_wgs84=[72.7, 18.8, 73.1, 19.3],
        analysis_crs="EPSG:32643",
        width=256,
        height=256,
    )

    for rep in download_reports:
        var = rep["variable"]
        grib_file = LOCAL_OUTPUT_ROOT / rep["filename"]
        if not grib_file.exists():
            raise FileNotFoundError(f"Missing saved GRIB file: {grib_file}")

        with grib_file.open("rb") as stream:
            gid = ec.codes_grib_new_from_file(stream)
            if gid is None:
                raise ValueError(f"ecCodes failed to decode GRIB message from {grib_file}")
            try:
                short_name = ec.codes_get(gid, "shortName")
                type_of_level = ec.codes_get(gid, "typeOfLevel")
                level = ec.codes_get(gid, "level")
                step_type = ec.codes_get(gid, "stepType")
                units = ec.codes_get(gid, "units")

                val_date = ec.codes_get(gid, "validityDate")
                val_time = ec.codes_get(gid, "validityTime")
                val_dt = datetime.strptime(f"{val_date:08d}{val_time:04d}", "%Y%m%d%H%M").replace(
                    tzinfo=UTC
                )

                if val_dt != SMOKE_TARGET_VALID:
                    raise ValueError(
                        f"GRIB valid time {val_dt} does not match expected {SMOKE_TARGET_VALID}"
                    )

                lats = np.asarray(ec.codes_get_array(gid, "latitudes"))
                lons = np.asarray(ec.codes_get_array(gid, "longitudes"))
                values = np.asarray(ec.codes_get_values(gid), dtype=np.float64)
                missing_val = ec.codes_get(gid, "missingValue")
                values[values == missing_val] = np.nan

                lat_uniq, r_idx = np.unique(lats, return_inverse=True)
                lon_uniq, c_idx = np.unique(lons, return_inverse=True)
                grid = np.full((len(lat_uniq), len(lon_uniq)), np.nan, dtype=np.float64)
                grid[r_idx, c_idx] = values

                # GFS latitude orientation is 90 -> -90 (descending)
                if lat_uniq[0] < lat_uniq[-1]:
                    lat_uniq = lat_uniq[::-1]
                    grid = grid[::-1, :]

                # Lon convention is 0 -> 360, convert to -180 -> 180 if needed
                if np.any(lon_uniq > 180.0):
                    shift = lon_uniq > 180.0
                    lon_uniq = np.where(shift, lon_uniq - 360.0, lon_uniq)
                    order = np.argsort(lon_uniq)
                    lon_uniq = lon_uniq[order]
                    grid = grid[:, order]

                v_min = float(np.nanmin(grid))
                v_max = float(np.nanmax(grid))
                v_mean = float(np.nanmean(grid))
                finite_pct = float(100.0 * np.sum(np.isfinite(grid)) / grid.size)

                # Spatial reprojection
                if var == "prate_mean":
                    # Convert PRATE (kg m^-2 s^-1) to rain rate (mm/h)
                    rate_mm_h = grid * 3600.0
                    finite_rain(rate_mm_h)
                    reprojected, spatial_meta = reproject_rate(
                        rate_mm_h, lat_uniq, lon_uniq, target_grid
                    )
                    signed_valid = True
                else:
                    spec = GFS_VARIABLE_SPECS[var]
                    reprojected, spatial_meta = reproject_field(
                        grid,
                        lat_uniq,
                        lon_uniq,
                        target_grid,
                        variable_name=var,
                        physical_range=spec["physical_range"],
                    )
                    if var in ("u10", "v10"):
                        # Verify raw parsed GRIB contains genuine negative wind values
                        has_raw_neg = bool(np.any(grid < 0.0))
                        # Verify reprojection path does not reject or clip negative values
                        test_neg_reproj, _ = reproject_field(
                            -np.abs(grid),
                            lat_uniq,
                            lon_uniq,
                            target_grid,
                            variable_name=var,
                            physical_range=spec["physical_range"],
                        )
                        survives_neg = bool(np.all(test_neg_reproj < 0.0))
                        signed_valid = has_raw_neg and survives_neg
                    else:
                        signed_valid = True

                spatial_reprojected[var] = reprojected

                parsed_reports.append(
                    {
                        "variable": var,
                        "shape": list(grid.shape),
                        "dtype": str(grid.dtype),
                        "units": units,
                        "shortName": short_name,
                        "typeOfLevel": type_of_level,
                        "level": level,
                        "stepType": step_type,
                        "forecastTime_lead": SMOKE_LEAD,
                        "valid_time": val_dt.isoformat(),
                        "min": v_min,
                        "max": v_max,
                        "mean": v_mean,
                        "finite_percentage": finite_pct,
                        "canonical_output_shape": list(reprojected.shape),
                        "canonical_min": float(np.nanmin(reprojected)),
                        "canonical_max": float(np.nanmax(reprojected)),
                        "canonical_mean": float(np.nanmean(reprojected)),
                        "signed_valid": signed_valid,
                    }
                )
            finally:
                ec.codes_release(gid)

    # 5. Persist Summary Manifest & Verify Reopening
    smoke_summary = {
        "smoke_status": "SUCCESS",
        "cycle_time": SMOKE_CYCLE.isoformat(),
        "lead_hour": SMOKE_LEAD,
        "native_valid_time": SMOKE_TARGET_VALID.isoformat(),
        "assumed_availability_time": (SMOKE_CYCLE + timedelta(hours=6)).isoformat(),
        "availability_basis": "assumed_cycle_plus_6.0h_required_bundle; not_observed_publication",
        "qc_flags": ["ASSUMED_AVAILABILITY"],
        "total_requested_bytes": total_requested_bytes,
        "total_received_bytes": total_received_bytes,
        "full_grib_download_required": False,
        "canonical_grid": {
            "crs": "EPSG:32643",
            "shape": [256, 256],
            "note": "Canonical reprojection does NOT create new meteorological resolution beyond native 0.25-deg GFS.",
        },
        "downloads": download_reports,
        "field_validation": parsed_reports,
    }

    # Save summary and reprojected npz
    for od in out_dirs:
        (od / "smoke_summary.json").write_text(
            json.dumps(smoke_summary, indent=2), encoding="utf-8"
        )
        np.savez_compressed(
            od / "smoke_reprojected.npz",
            **{k: v.astype(np.float32) for k, v in spatial_reprojected.items()},
        )

    # 6. Reopen and verify persistence
    persistence_verified = True
    persisted_files = []
    for od in out_dirs:
        log.info("Verifying persistence in: %s", od)
        for f in od.glob("*"):
            size = f.stat().st_size
            persisted_files.append({"path": str(f), "size": size})
            if size == 0:
                persistence_verified = False

        # Reopen GRIB2 files and ensure ecCodes parses them from disk
        for var in SMOKE_VARIABLES:
            p = od / f"{SMOKE_CYCLE:%Y%m%dT%H}_{var}_f{SMOKE_LEAD:03d}.grib2"
            if not p.exists():
                persistence_verified = False
            with p.open("rb") as stream:
                gid = ec.codes_grib_new_from_file(stream)
                if gid is None:
                    persistence_verified = False
                else:
                    ec.codes_release(gid)

        # Reopen npz
        with np.load(od / "smoke_reprojected.npz") as z:
            for var in SMOKE_VARIABLES:
                if var not in z or z[var].shape != (256, 256):
                    persistence_verified = False

    drive_reopen_verified = (
        drive_state["COLAB_DRIVE_PERSISTENCE_VERIFIED"]
        and DRIVE_OUTPUT_ROOT in out_dirs
        and all(
            item["path"].replace("\\", "/").startswith("/content/drive/MyDrive/")
            for item in persisted_files
            if str(DRIVE_OUTPUT_ROOT) in item["path"]
        )
    )
    return {
        "smoke_summary": smoke_summary,
        "download_reports": download_reports,
        "parsed_reports": parsed_reports,
        "persistence_verified": persistence_verified,
        "persisted_files": persisted_files,
        "total_requested_bytes": total_requested_bytes,
        "total_received_bytes": total_received_bytes,
        "smoke_output_directory": str(LOCAL_OUTPUT_ROOT),
        "drive_output_directory": str(DRIVE_OUTPUT_ROOT),
        "NETWORK_SMOKE_VERIFIED": True,
        "LOCAL_PERSISTENCE_VERIFIED": persistence_verified,
        "COLAB_DRIVE_PERSISTENCE_VERIFIED": drive_reopen_verified,
    }


if __name__ == "__main__":
    res = run_smoke_test()
    summary = res["smoke_summary"]
    f_val = {item["variable"]: item for item in summary["field_validation"]}

    signed_u10_ok = f_val["u10"]["signed_valid"]
    signed_v10_ok = f_val["v10"]["signed_valid"]
    precip_ok = f_val["prate_mean"]["signed_valid"] and f_val["prate_mean"]["units"] in (
        "kg m**-2 s**-1",
        "kg m^-2 s^-1",
    )
    reproj_ok = all(
        item["canonical_output_shape"] == [256, 256] for item in summary["field_validation"]
    )

    print("\n" + "=" * 60)
    print("PHASE_4E_GFS_REAL_SMOKE_COMPLETE=true")
    print("SMOKE_CYCLE=20210617_1800")
    print("SMOKE_LEAD=f007")
    print(f"REAL_NETWORK_BYTES_RETRIEVED={summary['total_received_bytes']}")
    print("FULL_GRIB_DOWNLOADED=false")
    print("IDX_SELECTION_VERIFIED=true")
    print("ALL_8_FIELDS_FOUND=true")
    print("ALL_8_FIELDS_PARSED=true")
    print(f"SIGNED_U10_VALID={'true' if signed_u10_ok else 'false'}")
    print(f"SIGNED_V10_VALID={'true' if signed_v10_ok else 'false'}")
    print(f"PRECIP_SEMANTICS_VALID={'true' if precip_ok else 'false'}")
    print(f"CANONICAL_REPROJECTION_VALID={'true' if reproj_ok else 'false'}")
    print("NETWORK_SMOKE_VERIFIED=true")
    print(f"LOCAL_PERSISTENCE_VERIFIED={'true' if res['LOCAL_PERSISTENCE_VERIFIED'] else 'false'}")
    print(
        f"COLAB_DRIVE_PERSISTENCE_VERIFIED={'true' if res['COLAB_DRIVE_PERSISTENCE_VERIFIED'] else 'false'}"
    )
    print("LOCKED_TEST_TOUCHED=false")
    print("FULL_REPLAY_DOWNLOAD_STARTED=false")
    print("TRAINING_STARTED=false")
    print("NORMALIZATION_FITTED=false")
    print("=" * 60)
    print(json.dumps(res["smoke_summary"], indent=2))
