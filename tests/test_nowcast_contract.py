from datetime import UTC, datetime

import numpy as np

from jalrakshak_ml.adapters.gpm import granule_filename, iter_half_hour_times
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast


def test_common_nowcast_result_manifest(tmp_path):
    result = PersistenceNowcast().predict_result(
        np.ones((4, 4), dtype=np.float32),
        4,
        issue_time=datetime(2023, 7, 25, tzinfo=UTC),
        data_version="gpm_v1",
    )
    assert result.rainfall.shape == (4, 4, 4)
    assert result.horizons_min == [30, 60, 90, 120]
    array_path, manifest_path = result.save(tmp_path)
    assert array_path.exists() and manifest_path.exists()
    assert result.to_manifest()["prediction_artifact_uri"] == str(array_path.resolve())


def test_gpm_native_timing_and_filename():
    start = datetime(2023, 7, 25, 0, 15, tzinfo=UTC)
    end = datetime(2023, 7, 25, 1, 30, tzinfo=UTC)
    times = list(iter_half_hour_times(start, end))
    assert [value.strftime("%H:%M") for value in times] == ["00:30", "01:00"]
    assert granule_filename(times[0]).endswith("S003000-E005959.0030.V07B.HDF5")
