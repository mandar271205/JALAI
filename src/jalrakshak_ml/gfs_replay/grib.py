"""Exact ecCodes selectors and bounded indexed retrieval of precipitation messages."""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
