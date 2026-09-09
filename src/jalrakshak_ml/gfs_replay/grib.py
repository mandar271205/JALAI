"""Exact ecCodes selectors and bounded indexed retrieval of precipitation messages."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import requests

from .core import source_uri, utc
from .spatial import crop_with_halo

_DLL_HANDLES = []


def eccodes_module():
    # Keep the DLL directory handle alive on Windows; Linux/Colab need no workaround.
    lib = Path(sys.prefix) / "Library" / "bin"
    if os.name == "nt" and lib.exists() and not _DLL_HANDLES:
        os.environ.setdefault("ECCODES_DIR", str(lib))
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
        _DLL_HANDLES.append(os.add_dll_directory(str(lib)))
    return importlib.import_module("eccodes")


def selector(product, cycle, lead):
    if product not in ("prate_mean", "apcp_interval") or not 1 <= lead <= 120:
        raise ValueError("Select a supported precipitation product at lead 1..120")
    # GFS surface flux statistics reset every six hours; require this exact product.
    return {
        "shortName": "prate" if product == "prate_mean" else "tp",
        "typeOfLevel": "surface",
        "level": 0,
        "stepType": "avg" if product == "prate_mean" else "accum",
        "startStep": ((lead - 1) // 6) * 6,
        "endStep": lead,
        "stepUnits": "h",
        "forecast_reference_time": utc(cycle).isoformat(),
    }


def choose_exact(messages: list[dict], requested: dict) -> dict:
    candidates = [m for m in messages if all(m.get(k) == v for k, v in requested.items())]
    if len(candidates) != 1:
        raise ValueError(f"Exact GRIB field missing or ambiguous: {len(candidates)} matches")
    return candidates[0]


def _time(date, time):
    return datetime.strptime(f"{int(date):08d}{int(time):04d}", "%Y%m%d%H%M").replace(tzinfo=UTC)


def read_field(path, requested, bbox):
    """Decode only the exact requested message; retain every statistical/time key."""
    ec = eccodes_module()
    match = None
    with Path(path).open("rb") as stream:
        while (gid := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                identity = {
                    key: ec.codes_get(gid, key)
                    for key in ("shortName", "typeOfLevel", "level", "stepType")
                }
                if any(identity[k] != requested[k] for k in identity):
                    continue
                step_units = ec.codes_get(gid, "stepUnits")
                if step_units not in (1, "h"):
                    raise ValueError("GRIB step units must be hours")
                meta = {
                    **identity,
                    "startStep": float(ec.codes_get(gid, "startStep")),
                    "endStep": float(ec.codes_get(gid, "endStep")),
                    "stepUnits": "h",
                    "units": ec.codes_get(gid, "units"),
                    "forecast_reference_time": _time(
                        ec.codes_get(gid, "dataDate"), ec.codes_get(gid, "dataTime")
                    ).isoformat(),
                    "valid_time": _time(
                        ec.codes_get(gid, "validityDate"), ec.codes_get(gid, "validityTime")
                    ).isoformat(),
                    "gridType": ec.codes_get(gid, "gridType"),
                    "paramId": ec.codes_get(gid, "paramId"),
                    "productDefinitionTemplateNumber": ec.codes_get(
                        gid, "productDefinitionTemplateNumber"
                    ),
                }
                if any(meta.get(k) != v for k, v in requested.items()):
                    continue
                if match is not None:
                    raise ValueError("Exact GRIB field ambiguous: multiple matches")
                if meta["gridType"] != "regular_ll":
                    raise ValueError("Expected regular latitude/longitude GFS grid")
                if utc(meta["valid_time"]) != utc(meta["forecast_reference_time"]) + timedelta(
                    hours=meta["endStep"]
                ):
                    raise ValueError("Inconsistent GRIB valid time")
                lats = np.asarray(ec.codes_get_array(gid, "latitudes"))
                lons = np.asarray(ec.codes_get_array(gid, "longitudes"))
                values = np.asarray(ec.codes_get_values(gid), dtype=np.float64)
                values[values == ec.codes_get(gid, "missingValue")] = np.nan
                lat, rows = np.unique(lats, return_inverse=True)
                lon, cols = np.unique(lons, return_inverse=True)
                if len(lat) * len(lon) != len(values) or len(
                    np.unique(rows * len(lon) + cols)
                ) != len(values):
                    raise ValueError("Duplicate/incomplete source coordinate grid")
                grid = np.full((len(lat), len(lon)), np.nan)
                grid[rows, cols] = values
                cropped, lat, lon, _ = crop_with_halo(grid, lat, lon, bbox)
                match = (cropped, lat, lon, meta)
            finally:
                ec.codes_release(gid)
    if match is None:
        raise ValueError(f"Exact GRIB field missing: {requested}")
    return match


def index_range(index_text: str, product: str, lead: int) -> tuple[int, int]:
    """Use the index for transport only; GRIB metadata is independently checked."""
    start = ((lead - 1) // 6) * 6
    variable, statistic = ("PRATE", "ave") if product == "prate_mean" else ("APCP", "acc")
    entries = [line.split(":") for line in index_text.splitlines() if line.strip()]
    matches = []
    for i, parts in enumerate(entries):
        if len(parts) >= 6 and parts[3:6] == [
            variable,
            "surface",
            f"{start}-{lead} hour {statistic} fcst",
        ]:
            if i + 1 == len(entries):
                raise ValueError("Index lacks next-message boundary")
            matches.append((int(parts[1]), int(entries[i + 1][1]) - 1))
    if len(matches) != 1:
        raise ValueError(f"Indexed precipitation missing/ambiguous: {len(matches)} matches")
    return matches[0]


def fetch_field(cycle, lead, cache_dir, product="prate_mean", *, allow_download=False):
    """Fetch one bounded message; never fall back to full-file transfer or another field."""
    requested = selector(product, cycle, lead)
    cache = Path(cache_dir)
    path = cache / f"{utc(cycle):%Y%m%dT%H}_{product}_f{lead:03d}.grib2"
    uri = source_uri(cycle, lead)
    if not path.exists():
        if not allow_download:
            raise FileNotFoundError(f"Missing cached field {path}; enable --download explicitly")
        with requests.get(uri + ".idx", timeout=30) as response:
            response.raise_for_status()
            begin, end = index_range(response.text, product, lead)
        size = end - begin + 1
        if not 16 <= size <= 16 * 1024 * 1024:
            raise ValueError("Precipitation message exceeds 16 MiB safety bound")
        with requests.get(
            uri, headers={"Range": f"bytes={begin}-{end}"}, stream=True, timeout=60
        ) as response:
            response.raise_for_status()
            expected = rf"bytes {begin}-{end}/\d+"
            if response.status_code != 206 or not re.fullmatch(
                expected, response.headers.get("Content-Range", "")
            ):
                raise ValueError("Server ignored or changed bounded byte-range request")
            data = response.raw.read(size + 1)
        if len(data) != size or data[:4] != b"GRIB" or data[-4:] != b"7777":
            raise ValueError("Truncated or invalid GRIB message")
        if int.from_bytes(data[8:16], "big") != size:
            raise ValueError("GRIB message size does not match requested range")
        cache.mkdir(parents=True, exist_ok=True)
        # Exclusive creation: cached source messages are immutable.
        with path.open("xb") as stream:
            stream.write(data)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, requested, {"source_uri": uri, "source_message_sha256": digest}


RICH_VARIABLE_IDX_PATTERNS: dict[str, tuple[str, str | tuple[str, ...], str]] = {
    "u10": ("UGRD", "10 m above ground", "instant"),
    "v10": ("VGRD", "10 m above ground", "instant"),
    "t2m": ("TMP", "2 m above ground", "instant"),
    "rh2m": ("RH", "2 m above ground", "instant"),
    "sp": ("PRES", "surface", "instant"),
    "cape": ("CAPE", "surface", "instant"),
    "pwat": (
        "PWAT",
        ("entire atmosphere", "entire atmosphere (considered as a single layer)"),
        "instant",
    ),
    "prate_mean": ("PRATE", "surface", "interval_avg"),
    "apcp_interval": ("APCP", "surface", "interval_accum"),
}


def rich_index_ranges(
    index_text: str,
    variable_keys: Sequence[str] | None = None,
    lead: int = 1,
    *,
    lead_hour: int | None = None,
) -> dict[str, tuple[int, int]]:
    """Determine byte ranges for requested rich GFS variables from NOAA .idx inventory.

    Enforces:
    - strict field identity (variable, level, step semantics)
    - failure on missing field
    - failure on ambiguous field
    - failure on missing boundary
    - safety size bound [16 B, 16 MiB]
    """
    if lead_hour is not None:
        lead = lead_hour
    if variable_keys is None:
        variable_keys = ("prate_mean", "u10", "v10", "t2m", "rh2m", "sp", "cape", "pwat")
    if not 1 <= lead <= 120:
        raise ValueError("Lead must be between 1 and 120 hours")
    entries = [line.split(":") for line in index_text.splitlines() if line.strip()]
    if not entries:
        raise ValueError("Empty or invalid .idx inventory text")

    start_accum = ((lead - 1) // 6) * 6
    ranges: dict[str, tuple[int, int]] = {}

    alias_map = {"prate": "prate_mean", "tp": "apcp_interval"}

    all_var_matches: dict[str, tuple[str, str, str, str, list[tuple[int, int]]]] = {}
    for raw_var in variable_keys:
        var = alias_map.get(raw_var, raw_var)
        if var not in RICH_VARIABLE_IDX_PATTERNS:
            raise ValueError(f"Unsupported variable key for rich GFS index: {raw_var!r}")

        expected_var, expected_level, step_mode = RICH_VARIABLE_IDX_PATTERNS[var]
        if step_mode == "instant":
            expected_step = f"{lead} hour fcst"
        elif step_mode == "interval_avg":
            expected_step = f"{start_accum}-{lead} hour ave fcst"
        elif step_mode == "interval_accum":
            expected_step = f"{start_accum}-{lead} hour acc fcst"
        else:
            raise ValueError(f"Unknown step mode {step_mode} for {var}")

        matches = []
        for i, parts in enumerate(entries):
            if (
                len(parts) >= 6
                and parts[3] == expected_var
                and parts[4]
                in ((expected_level,) if isinstance(expected_level, str) else expected_level)
                and parts[5] == expected_step
            ):
                begin = int(parts[1])
                end = int(entries[i + 1][1]) - 1 if (i + 1 < len(entries)) else -1
                matches.append((begin, end))
        all_var_matches[raw_var] = (var, expected_var, expected_level, expected_step, matches)

    # 1. Check for ambiguous / duplicate matches first
    for raw_var, (
        var,
        expected_var,
        expected_level,
        expected_step,
        matches,
    ) in all_var_matches.items():
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous GRIB field in .idx: {raw_var!r} matched {len(matches)} times at lead {lead}"
            )

    # 2. Check for missing matches second
    for raw_var, (
        var,
        expected_var,
        expected_level,
        expected_step,
        matches,
    ) in all_var_matches.items():
        if len(matches) == 0:
            raise ValueError(
                f"Missing required GRIB messages in .idx: exact GRIB field missing for {raw_var!r} at lead {lead}: "
                f"expected ({expected_var}, {expected_level}, {expected_step})"
            )

    # 3. Check boundaries and size limits, then construct ranges
    for raw_var, (
        var,
        expected_var,
        expected_level,
        expected_step,
        matches,
    ) in all_var_matches.items():
        begin, end = matches[0]
        if end == -1:
            raise ValueError(f"Index lacks next-message boundary for {raw_var}")
        size = end - begin + 1
        if not 16 <= size <= 16 * 1024 * 1024:
            raise ValueError(f"GRIB message size {size} out of bounds [16 B, 16 MiB] for {raw_var}")

        ranges[var] = (begin, end)
        if raw_var != var:
            ranges[raw_var] = (begin, end)
        elif var == "prate_mean":
            ranges["prate"] = (begin, end)

    return ranges


def fetch_rich_gfs_lead(
    cycle: str | datetime | None = None,
    lead: int | None = None,
    cache_dir: str | Path | None = None,
    variable_keys: Sequence[str] = (
        "u10",
        "v10",
        "t2m",
        "rh2m",
        "sp",
        "cape",
        "pwat",
        "prate_mean",
    ),
    *,
    cycle_dt: str | datetime | None = None,
    lead_hour: int | None = None,
    allow_download: bool = False,
    dry_run: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch or plan byte-range retrieval for all requested rich variables at (cycle, lead).

    In dry_run mode, verifies URLs and planned ranges without downloading GRIB payloads.
    Never falls back to full global GRIB files.
    """
    if cycle is None:
        if cycle_dt is None:
            raise ValueError("cycle or cycle_dt must be provided")
        cycle = cycle_dt
    if lead is None:
        if lead_hour is None:
            raise ValueError("lead or lead_hour must be provided")
        lead = lead_hour
    if cache_dir is None:
        cache_dir = Path("data/cache/gfs")

    cycle_dt_val = utc(cycle)
    uri = source_uri(cycle_dt_val, lead)
    cache = Path(cache_dir)
    http = session or requests

    results: dict[str, dict[str, Any]] = {}

    all_cached = True
    for var in variable_keys:
        p = cache / f"{cycle_dt_val:%Y%m%dT%H}_{var}_f{lead:03d}.grib2"
        if not p.exists():
            all_cached = False
            break

    if all_cached and not dry_run:
        for var in variable_keys:
            p = cache / f"{cycle_dt_val:%Y%m%dT%H}_{var}_f{lead:03d}.grib2"
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            results[var] = {
                "path": p,
                "status": "CACHED",
                "source_uri": uri,
                "sha256": digest,
            }
        return results

    if not allow_download and not dry_run:
        raise FileNotFoundError(
            f"Missing cached rich fields for cycle {cycle_dt_val.isoformat()} lead {lead} at {cache}; "
            f"enable --download explicitly."
        )

    if dry_run:
        dry_ranges = {}
        for var in variable_keys:
            p = cache / f"{cycle_dt_val:%Y%m%dT%H}_{var}_f{lead:03d}.grib2"
            var_info = {
                "destination_path": str(p),
                "source_uri": uri,
                "index_uri": uri + ".idx",
                "variable": var,
                "cycle": cycle_dt_val.isoformat(),
                "lead": lead,
                "status": "PLANNED_DRY_RUN",
                "full_grib_download_required": False,
            }
            results[var] = var_info
            dry_ranges[var] = var_info
        return {
            "status": "dry_run",
            "full_grib_download_required": False,
            "ranges": dry_ranges,
            "variables": results,
            **results,
        }

    with http.get(uri + ".idx", timeout=30) as resp:
        resp.raise_for_status()
        idx_text = resp.text

    ranges = rich_index_ranges(idx_text, variable_keys, lead)

    cache.mkdir(parents=True, exist_ok=True)
    for var, (begin, end) in ranges.items():
        p = cache / f"{cycle_dt_val:%Y%m%dT%H}_{var}_f{lead:03d}.grib2"
        if p.exists():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            results[var] = {
                "path": p,
                "status": "ALREADY_CACHED",
                "source_uri": uri,
                "byte_range": [begin, end],
                "sha256": digest,
            }
            continue

        size = end - begin + 1
        with http.get(
            uri,
            headers={"Range": f"bytes={begin}-{end}"},
            stream=True,
            timeout=60,
        ) as resp:
            resp.raise_for_status()
            expected = rf"bytes {begin}-{end}/\d+"
            if resp.status_code != 206 or not re.fullmatch(
                expected, resp.headers.get("Content-Range", "")
            ):
                raise ValueError("Server ignored or altered bounded byte-range request")
            data = resp.raw.read(size + 1)

        if len(data) != size or data[:4] != b"GRIB" or data[-4:] != b"7777":
            raise ValueError(f"Truncated or invalid GRIB message for {var}")
        if int.from_bytes(data[8:16], "big") != size:
            raise ValueError(f"GRIB message size does not match requested range for {var}")

        with p.open("xb") as f:
            f.write(data)

        digest = hashlib.sha256(data).hexdigest()
        results[var] = {
            "path": p,
            "status": "DOWNLOADED",
            "source_uri": uri,
            "byte_range": [begin, end],
            "downloaded_bytes": len(data),
            "sha256": digest,
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    return results
