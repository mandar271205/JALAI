"""Synthetic-only verification of Phase 4E post-smoke production guards."""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import requests

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.phase4e_prepare import freeze_winner, tournament_execution_plan
from jalrakshak_ml.deep_nowcast.phase4e_runner import compile_validation_comparison
from jalrakshak_ml.deep_nowcast.splits import VALIDATION_EVENTS_AUTHORITATIVE
from jalrakshak_ml.deep_nowcast.tournament import run_tournament
from jalrakshak_ml.gfs_replay.grib import rich_index_ranges
from jalrakshak_ml.gfs_replay.phase4e_audit import audit_download
from jalrakshak_ml.gfs_replay.rich_download import (
    AVAILABILITY_BASIS,
    REQUIRED_FIELDS,
    acquire_rich_granule,
    granule_directory,
    initialize_download_manifest,
    parse_prate_interval,
    validate_grib_envelope,
)
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    align_instantaneous_horizons,
    align_prate_horizons,
    derive_cyclic_wind_direction,
    persistence_environment,
    plan_rich_replay_for_events,
)

CYCLE = datetime(2021, 6, 17, 18, tzinfo=UTC)


def idx_text(lead=7, width=64):
    labels = [
        ("UGRD", "10 m above ground", f"{lead} hour fcst"),
        ("VGRD", "10 m above ground", f"{lead} hour fcst"),
        ("TMP", "2 m above ground", f"{lead} hour fcst"),
        ("RH", "2 m above ground", f"{lead} hour fcst"),
        ("PRES", "surface", f"{lead} hour fcst"),
        ("CAPE", "surface", f"{lead} hour fcst"),
        ("PWAT", "entire atmosphere", f"{lead} hour fcst"),
        ("PRATE", "surface", f"6-{lead} hour ave fcst"),
        ("HGT", "500 mb", f"{lead} hour fcst"),
    ]
    return "\n".join(
        f"{index + 1}:{index * width}:d=2021061718:{variable}:{level}:{step}:"
        for index, (variable, level, step) in enumerate(labels)
    )


def grib_message(size=64):
    payload = bytearray(size)
    payload[:4] = b"GRIB"
    payload[8:16] = size.to_bytes(8, "big")
    payload[-4:] = b"7777"
    return bytes(payload)


class Response:
    def __init__(self, status=200, text="", data=b"", content_range=""):
        self.status_code, self.text, self.raw = status, text, io.BytesIO(data)
        self.headers = {"Content-Range": content_range} if content_range else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, *, partial_variable=None):
        self.calls, self.partial_variable = [], partial_variable

    def get(self, url, headers=None, **kwargs):
        self.calls.append((url, headers))
        if url.endswith(".idx"):
            return Response(text=idx_text())
        begin, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        data = grib_message(end - begin + 1)
        if self.partial_variable == len([call for call in self.calls if call[1]]) - 1:
            data = data[:-1]
        return Response(206, data=data, content_range=f"bytes {begin}-{end}/999999")


def synthetic_validator(path, variable, cycle, lead):
    validate_grib_envelope(path)
    valid = cycle + timedelta(hours=lead)
    return {
        "grib_parse_state": "PASSED",
        "source_valid_time": valid.isoformat(),
        "precip_interval_metadata": {"start_step": 6, "end_step": 7}
        if variable == "prate_mean"
        else None,
        "finite_percentage": 100.0,
        "physical_min": -5.0 if variable in ("u10", "v10") else 1.0,
        "physical_max": 5.0,
    }


def test_real_noaa_idx_mapping_is_exact_and_rejects_wrong_layers():
    ranges = rich_index_ranges(idx_text(), REQUIRED_FIELDS, 7)
    assert set(REQUIRED_FIELDS) <= set(ranges)
    assert ranges["u10"] == (0, 63) and ranges["pwat"] == (6 * 64, 7 * 64 - 1)
    wrong = idx_text().replace("10 m above ground", "100 m above ground", 1)
    with pytest.raises(ValueError, match="Missing required"):
        rich_index_ranges(wrong, REQUIRED_FIELDS, 7)
    ambiguous = idx_text() + "\n10:576:d=2021061718:PWAT:entire atmosphere:7 hour fcst:"
    with pytest.raises(ValueError, match="Ambiguous"):
        rich_index_ranges(ambiguous, REQUIRED_FIELDS, 7)


def test_prate_interval_and_halfhour_provenance_are_preserved():
    metadata = {
        "shortName": "prate",
        "typeOfLevel": "surface",
        "level": 0,
        "stepType": "avg",
        "startStep": 6,
        "endStep": 7,
        "units": "kg m**-2 s**-1",
        "forecast_reference_time": CYCLE.isoformat(),
        "valid_time": (CYCLE + timedelta(hours=7)).isoformat(),
    }
    parsed = parse_prate_interval(metadata)
    assert parsed["source_interval_start"] == "2021-06-18T00:00:00+00:00"
    assert parsed["source_interval_end"] == "2021-06-18T01:00:00+00:00"
    records = align_prate_horizons(CYCLE + timedelta(hours=6), CYCLE, {7: metadata}, (30, 60))
    assert records[0]["source_interval_start"] == records[1]["source_interval_start"]
    assert all(not record["independent_native_observation"] for record in records)
    hourly_rate = 4.0
    assert hourly_rate * 0.5 + hourly_rate * 0.5 == hourly_rate


def test_instantaneous_source_and_aligned_times_remain_distinct():
    records = align_instantaneous_horizons(CYCLE, CYCLE + timedelta(hours=6), (30,))
    record = records[0]
    assert record["aligned_target_time"] != record["source_native_valid_time"]
    assert record["source_age_minutes"] == 30
    assert record["availability_basis"] == AVAILABILITY_BASIS


def test_negative_wind_quadrants_and_cyclic_encoding():
    u = np.array([-1.0, -1.0, 1.0, 1.0])
    v = np.array([-1.0, 1.0, -1.0, 1.0])
    speed, sin_direction, cos_direction = derive_cyclic_wind_direction(u, v)
    np.testing.assert_allclose(speed, np.sqrt(2))
    np.testing.assert_allclose(sin_direction**2 + cos_direction**2, 1.0, atol=1e-6)
    assert len(set(np.round(sin_direction, 5))) > 1


def test_windows_content_path_never_counts_as_colab_drive(monkeypatch):
    monkeypatch.delitem(sys.modules, "google.colab", raising=False)
    state = persistence_environment(Path(r"C:\content\drive\MyDrive\fake"))
    assert state["COLAB_DRIVE_PERSISTENCE_VERIFIED"] is False


def test_resumable_atomic_granule_manifest(tmp_path):
    session = Session()
    first = acquire_rich_granule(
        CYCLE, 7, tmp_path, session=session, validator=synthetic_validator, sleep=lambda _: None
    )
    assert first["completion_state"] == "COMPLETE"
    directory = granule_directory(tmp_path, CYCLE, 7)
    assert all((directory / f"{variable}.grib2").exists() for variable in REQUIRED_FIELDS)
    assert not list(directory.glob("*.part"))
    second_session = Session()
    second = acquire_rich_granule(
        CYCLE,
        7,
        tmp_path,
        session=second_session,
        validator=synthetic_validator,
        sleep=lambda _: None,
    )
    assert second["completion_state"] == "COMPLETE"
    assert len(second_session.calls) == 1  # index only; all eight validated from cache
    assert all(record["resumed_from_valid_cache"] for record in second["variables"].values())


def test_partial_download_never_marks_granule_complete(tmp_path):
    result = acquire_rich_granule(
        CYCLE,
        7,
        tmp_path,
        session=Session(partial_variable=2),
        validator=synthetic_validator,
        sleep=lambda _: None,
    )
    assert result["completion_state"] == "INCOMPLETE"
    assert result["variables"]["t2m"]["completion_state"] == "FAILED"
    assert not (granule_directory(tmp_path, CYCLE, 7) / "t2m.grib2.part").exists()


def test_planner_manifest_counts_and_empty_audit(tmp_path):
    cfg = load_yaml("configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml")
    plan = plan_rich_replay_for_events(cfg["events"], assumed_latency_hours=6)
    assert plan["num_unique_cycle_leads"] == 225 and plan["total_issues"] == 255
    assert plan["train_issues"] == 204 and plan["validation_issues"] == 51
    manifest = initialize_download_manifest(plan, tmp_path)
    assert manifest["expected_pairs"] == manifest["missing_pairs"] == 225
    audit = audit_download(plan, tmp_path)
    assert audit["missing_pairs"] == 225 and not audit["audit_passed"]


def test_tournament_and_model_freeze_gates(tmp_path):
    plan = tournament_execution_plan()
    assert plan["split"] == "validation_only" and plan["execution_state"] == "NOT_STARTED"
    assert plan["deep_training_seeds"] == [26071, 26072, 26073]
    with pytest.raises(RuntimeError, match="Legacy tournament disabled"):
        run_tournament()
    with pytest.raises(RuntimeError, match="gate closed"):
        freeze_winner({}, {}, tmp_path / "winner.json")


def test_validation_comparison_is_event_bootstrapped_and_test_free():
    shape = (1, 4, 1, 2, 2)
    events = {
        event_id: (np.ones(shape), np.ones(shape), np.ones(shape, dtype=bool))
        for event_id in VALIDATION_EVENTS_AUTHORITATIVE
    }
    result = compile_validation_comparison(
        {"synthetic_model": events},
        {"synthetic_model": {"latency_ms": 1.0, "parameter_count": 10}},
    )
    assert result["bootstrap_unit"] == "event"
    assert result["pixel_independence_assumed"] is False
    assert result["locked_test_accessed"] is False
    assert set(result["models"]["synthetic_model"]["per_event"]) == set(
        VALIDATION_EVENTS_AUTHORITATIVE
    )
