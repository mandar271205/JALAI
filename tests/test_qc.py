"""Tests for QC framework and WeatherFrame schema."""
from datetime import datetime, timezone

import numpy as np
import pytest

from jalrakshak_ml.qc.frame_qc import FrameQC
from jalrakshak_ml.schemas.weather_frame import WeatherFrame


def make_qc(**kwargs) -> FrameQC:
    defaults = dict(
        source="test_source",
        variable="rainfall_rate",
        data_version="test_v1",
        source_resolution="0.1 deg",
        canonical_resolution="~120m @ 256x256",
        processing_version="0.1.0",
        units="mm/h",
    )
    defaults.update(kwargs)
    return FrameQC(**defaults)


class TestWeatherFrameSchema:

    def test_valid_frame(self):
        frame = WeatherFrame(
            source="gpm_imerg",
            variable="rainfall_rate",
            valid_time=datetime(2023, 7, 1, 0, 0, tzinfo=timezone.utc),
            quality_score=0.95,
            missing_percent=2.5,
            processing_version="0.2.0",
            data_version="IMERG_V07",
            source_resolution="0.1 deg",
            canonical_resolution="~120m",
            units="mm/h",
            acquisition_timestamp=datetime.now(timezone.utc),
            checksum="abc123",
        )
        assert frame.is_usable()
        assert frame.source == "gpm_imerg"

    def test_unusable_frame_high_missing(self):
        frame = WeatherFrame(
            source="gpm_imerg",
            variable="rainfall_rate",
            valid_time=datetime(2023, 7, 1, tzinfo=timezone.utc),
            quality_score=0.4,
            missing_percent=95.0,
            processing_version="0.2.0",
            data_version="IMERG_V07",
            source_resolution="0.1 deg",
            canonical_resolution="~120m",
            units="mm/h",
            acquisition_timestamp=datetime.now(timezone.utc),
            checksum="abc123",
        )
        assert not frame.is_usable()

    def test_quality_score_bounds(self):
        with pytest.raises(Exception):
            WeatherFrame(
                source="x", variable="x",
                valid_time=datetime.now(timezone.utc),
                quality_score=1.5,   # out of bounds
                missing_percent=0,
                processing_version="0", data_version="0",
                source_resolution="x", canonical_resolution="x",
                units="x", acquisition_timestamp=datetime.now(timezone.utc),
                checksum="x",
            )


class TestFrameQC:

    def test_clean_array_passes(self):
        qc = make_qc()
        arr = np.random.uniform(0, 10, (256, 256)).astype(np.float32)
        valid_time = datetime(2023, 7, 1, tzinfo=timezone.utc)
        manifest, cleaned = qc.run(arr, valid_time)
        assert manifest.quality_score >= 0.9
        assert manifest.missing_percent == 0.0
        assert manifest.source == "test_source"
        assert len(manifest.checksum) == 64  # sha256 hex

    def test_mostly_missing_gets_penalised(self):
        qc = make_qc()
        arr = np.full((256, 256), np.nan, dtype=np.float32)
        arr[0:10, 0:10] = 5.0  # only a tiny patch
        manifest, _ = qc.run(arr, datetime(2023, 7, 1, tzinfo=timezone.utc))
        assert manifest.missing_percent > 90.0
        assert manifest.quality_score < 0.5
        assert any("MISSING" in f for f in manifest.qc_flags)

    def test_out_of_range_values_clipped(self):
        qc = make_qc(variable="rainfall_rate")
        arr = np.full((256, 256), 500.0, dtype=np.float32)  # above 300 mm/h limit
        manifest, cleaned = qc.run(arr, datetime(2023, 7, 1, tzinfo=timezone.utc))
        assert any("OUT_OF_RANGE" in f for f in manifest.qc_flags)
        assert float(cleaned.max()) <= 300.0

    def test_duplicate_detection(self):
        seen: set[str] = set()
        qc1 = make_qc(seen_timestamps=seen)
        qc2 = make_qc(seen_timestamps=seen)
        arr = np.zeros((256, 256), dtype=np.float32)
        t = datetime(2023, 7, 1, tzinfo=timezone.utc)
        m1, _ = qc1.run(arr, t)
        m2, _ = qc2.run(arr, t)
        assert not any("DUPLICATE" in f for f in m1.qc_flags)
        assert any("DUPLICATE" in f for f in m2.qc_flags)

    def test_naive_timestamp_flagged(self):
        qc = make_qc()
        arr = np.zeros((256, 256), dtype=np.float32)
        naive_time = datetime(2023, 7, 1)  # no tzinfo
        manifest, _ = qc.run(arr, naive_time)
        assert any("NAIVE_TIMESTAMP" in f for f in manifest.qc_flags)
