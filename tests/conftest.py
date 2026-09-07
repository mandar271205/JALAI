from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
import zarr


@pytest.fixture
def phase3_version_dir(tmp_path):
    version_dir = tmp_path / "gpm_test_v1"
    events_dir = version_dir / "events"
    events_dir.mkdir(parents=True)
    records = []
    specifications = [
        ("storm_train", "train", datetime(2023, 7, 1, tzinfo=UTC), 1.0),
        ("storm_validation", "validation", datetime(2023, 7, 10, tzinfo=UTC), 20.0),
        ("storm_test", "test", datetime(2023, 7, 20, tzinfo=UTC), 40.0),
    ]
    for event_id, split, start, offset in specifications:
        path = events_dir / f"{event_id}.zarr"
        root = zarr.open(str(path), mode="w")
        rainfall = np.stack([
            np.full((8, 8), offset + index * 0.1, dtype=np.float32)
            for index in range(10)
        ])
        rainfall[:, 0, 0] = np.nan
        valid = np.isfinite(rainfall)
        times = [(start + timedelta(minutes=30 * index)).isoformat() for index in range(10)]
        for name, values, dtype, chunks in [
            ("rainfall", rainfall, "float32", (4, 8, 8)),
            ("valid_mask", valid, "bool", (4, 8, 8)),
        ]:
            array = root.create_array(name, shape=values.shape, chunks=chunks, dtype=dtype)
            array[:] = values
        time_array = root.create_array("time", shape=(10,), chunks=(10,), dtype="str")
        time_array[:] = np.asarray(times, dtype=str)
        root.attrs.update({
            "event_id": event_id,
            "split": split,
            "data_version": "gpm_test_v1",
            "expected_frames": 10,
            "source_resolution": "0.1 deg",
            "canonical_resolution": "8x8 test",
        })
        records.append({
            "event_id": event_id,
            "split": split,
            "path": path.relative_to(version_dir).as_posix(),
            "start": times[0],
            "end": (start + timedelta(minutes=30 * 10)).isoformat(),
            "expected_frames": 10,
            "actual_frames": 10,
        })
    (version_dir / "manifest.json").write_text(json.dumps({
        "data_version": "gpm_test_v1",
        "source": "test",
        "source_version": "test",
        "temporal_step_minutes": 30,
        "events": records,
    }), encoding="utf-8")
    return version_dir
