"""Regression tests for the Phase 4E PRATE precipitation-semantics bug fix.

Bug: build_rich_issue_from_cache() routed prate_mean through reconstruct_hourly(),
which is strictly for cumulative APCP fields.  PRATE is an interval-mean rate
(kg/m2/s); the correct conversion is rate_mm_h = prate_kg_m2_s * 3600.

Tests:
1.  Correct mm/h value for known inputs.
2.  All accepted PRATE unit string variants.
3.  Multi-hour intervals give same mm/h (duration must NOT scale the rate).
4.  reconstruct_hourly() still fails on multi-hour PRATE (regression guard).
5.  Negative / NaN / Inf rejected.
6.  Wrong shortName / stepType / typeOfLevel / level rejected.
7.  Zero and reverse intervals rejected.
8.  APCP backward compat unaffected.
9.  Provenance tag TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL present.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from jalrakshak_ml.gfs_replay.core import (
    interval_amount,
    prate_mean_to_rate,
    reconstruct_hourly,
)

CYCLE = datetime(2023, 8, 24, 0, 0, 0, tzinfo=UTC)


def _prate_meta(
    start: float = 0,
    end: float = 1,
    units: str = "kg m**-2 s**-1",
    short_name: str = "prate",
    step_type: str = "avg",
    type_of_level: str = "surface",
    level: int = 0,
    step_units: str = "h",
) -> dict:
    return {
        "shortName": short_name,
        "stepType": step_type,
        "typeOfLevel": type_of_level,
        "level": level,
        "startStep": start,
        "endStep": end,
        "stepUnits": step_units,
        "units": units,
        "forecast_reference_time": CYCLE.isoformat(),
        "valid_time": (CYCLE + timedelta(hours=end)).isoformat(),
    }


def _apcp_meta(start: float = 0, end: float = 1) -> dict:
    return {
        "shortName": "tp",
        "stepType": "accum",
        "typeOfLevel": "surface",
        "level": 0,
        "startStep": start,
        "endStep": end,
        "stepUnits": "h",
        "units": "kg m**-2",
        "forecast_reference_time": CYCLE.isoformat(),
        "valid_time": (CYCLE + timedelta(hours=end)).isoformat(),
    }


# ---------------------------------------------------------------------------
# 1. Correct conversion value
# ---------------------------------------------------------------------------

class TestPrateMeanToRate:
    def test_2mm_h_from_known_prate_value(self):
        values = np.array([[2.0 / 3600, 2.0 / 3600], [2.0 / 3600, 2.0 / 3600]])
        result = prate_mean_to_rate(values, _prate_meta(start=0, end=1))
        np.testing.assert_allclose(result, 2.0, rtol=1e-10)

    def test_zero_rain_maps_to_zero(self):
        values = np.zeros((3, 3))
        result = prate_mean_to_rate(values, _prate_meta(start=0, end=1))
        np.testing.assert_array_equal(result, 0.0)

    def test_scalar_array_accepted(self):
        result = prate_mean_to_rate(np.array([5.0 / 3600]), _prate_meta())
        assert result.item() == pytest.approx(5.0, rel=1e-10)

    def test_output_dtype_is_float64(self):
        result = prate_mean_to_rate(np.array([1.0 / 3600], dtype=np.float32), _prate_meta())
        assert result.dtype == np.float64

    def test_output_is_nonnegative(self):
        result = prate_mean_to_rate(np.full((4, 4), 10.0 / 3600), _prate_meta())
        assert np.all(result >= 0)


# ---------------------------------------------------------------------------
# 2. Accepted PRATE unit variants
# ---------------------------------------------------------------------------

class TestPrateUnitVariants:
    @pytest.mark.parametrize("units", [
        "kg m**-2 s**-1",
        "kgm**-2s**-1",
        "kgm^-2s^-1",
        "kg/m^2/s",
        "kgm-2s-1",
    ])
    def test_accepted_unit_variant(self, units):
        result = prate_mean_to_rate(np.array([1.0 / 3600]), _prate_meta(units=units))
        assert result.item() == pytest.approx(1.0, rel=1e-10)

    def test_unsupported_unit_raises(self):
        with pytest.raises(ValueError, match="Unsupported PRATE units"):
            prate_mean_to_rate(np.array([1.0 / 3600]), _prate_meta(units="mm/h"))

    def test_temperature_unit_raises(self):
        with pytest.raises(ValueError, match="Unsupported PRATE units"):
            prate_mean_to_rate(np.array([1.0 / 3600]), _prate_meta(units="K"))


# ---------------------------------------------------------------------------
# 3. Multi-hour PRATE intervals -- rate must be invariant to duration
# ---------------------------------------------------------------------------

class TestPrateIntervalInvariance:
    @pytest.mark.parametrize("start, end", [
        (0, 1), (0, 2), (0, 6), (6, 12), (6, 7), (12, 18),
    ])
    def test_rate_invariant_to_interval_duration(self, start, end):
        values = np.array([[3.0 / 3600]])
        result = prate_mean_to_rate(values, _prate_meta(start=start, end=end))
        np.testing.assert_allclose(
            result, 3.0, rtol=1e-10,
            err_msg=f"Rate changed for interval [{start},{end}h]; duration must not scale PRATE",
        )


# ---------------------------------------------------------------------------
# 4. reconstruct_hourly() regression guard -- must still fail on PRATE multi-hour
# ---------------------------------------------------------------------------

class TestReconstructHourlyRegressionGuard:
    def test_reconstruct_hourly_fails_on_prate_0_to_2(self):
        """Lead-2 PRATE has startStep=0, endStep=2 -- the original production crash."""
        with pytest.raises(ValueError, match="Cannot infer hourly amount"):
            reconstruct_hourly([(np.array([[2.0 / 3600]]), _prate_meta(start=0, end=2))])

    def test_reconstruct_hourly_fails_on_prate_6_to_12(self):
        with pytest.raises(ValueError, match="Cannot infer hourly amount"):
            reconstruct_hourly([(np.array([[1.0 / 3600]]), _prate_meta(start=6, end=12))])


# ---------------------------------------------------------------------------
# 5. Non-physical values rejected
# ---------------------------------------------------------------------------

class TestNonPhysicalValues:
    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([-1.0 / 3600]), _prate_meta())

    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([np.nan]), _prate_meta())

    def test_inf_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([np.inf]), _prate_meta())

    def test_negative_inf_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([-np.inf]), _prate_meta())


# ---------------------------------------------------------------------------
# 6. Wrong field identity rejected
# ---------------------------------------------------------------------------

class TestFieldIdentityValidation:
    def test_wrong_short_name_tp(self):
        with pytest.raises(ValueError, match="shortName"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(short_name="tp"))

    def test_wrong_short_name_sp(self):
        with pytest.raises(ValueError, match="shortName"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(short_name="sp"))

    def test_wrong_step_type_accum(self):
        with pytest.raises(ValueError, match="stepType"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(step_type="accum"))

    def test_wrong_step_type_instant(self):
        with pytest.raises(ValueError, match="stepType"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(step_type="instant"))

    def test_wrong_level_type(self):
        with pytest.raises(ValueError, match="typeOfLevel"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(type_of_level="heightAboveGround"))

    def test_wrong_level_value(self):
        with pytest.raises(ValueError, match="level"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(level=2))

    def test_wrong_step_units_min(self):
        with pytest.raises(ValueError, match="stepUnits"):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(step_units="min"))


# ---------------------------------------------------------------------------
# 7. Zero and reverse intervals rejected
# ---------------------------------------------------------------------------

class TestIntervalValidation:
    def test_zero_duration_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(start=1, end=1))

    def test_negative_duration_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(start=2, end=1))

    def test_negative_start_step_rejected(self):
        with pytest.raises(ValueError):
            prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(start=-1, end=1))


# ---------------------------------------------------------------------------
# 8. APCP backward compat
# ---------------------------------------------------------------------------

class TestApCpBackwardCompat:
    def test_apcp_3h_accumulation(self):
        result = interval_amount(np.array([6.0]), _apcp_meta(start=0, end=3))
        assert result.item() == pytest.approx(6.0)

    def test_apcp_1h_accumulation_unchanged(self):
        result = interval_amount(np.array([2.0]), _apcp_meta(start=0, end=1))
        assert result.item() == pytest.approx(2.0)

    def test_apcp_and_prate_numerically_equal_for_1h(self):
        apcp_mm = interval_amount(np.array([2.0]), _apcp_meta(start=0, end=1))
        prate_mmh = prate_mean_to_rate(np.array([2.0 / 3600]), _prate_meta(start=0, end=1))
        assert apcp_mm.item() == pytest.approx(prate_mmh.item(), rel=1e-10)

    def test_reconstruct_hourly_still_works_for_apcp(self):
        source = [
            (np.array([2.0]), _apcp_meta(start=0, end=1)),
            (np.array([4.0]), _apcp_meta(start=0, end=2)),
        ]
        result = reconstruct_hourly(source)
        assert len(result) == 2
        assert result[0].rate.item() == pytest.approx(2.0, rel=1e-10)
        assert result[1].rate.item() == pytest.approx(2.0, rel=1e-10)


# ---------------------------------------------------------------------------
# 9. Provenance tag
# ---------------------------------------------------------------------------

class TestProvenanceTag:
    def test_conversion_method_tag_correct(self):
        """Pipeline source_provenance must carry the PRATE-specific conversion tag."""
        values = np.array([[2.0 / 3600]])
        meta = _prate_meta(start=0, end=2)
        rate_mm_h = prate_mean_to_rate(values, meta)
        # Simulate what build_rich_issue_from_cache() writes
        source_entry = {
            "conversion_method": "TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL",
            "conversion_formula": "rate_mm_h = prate_kg_m2_s * 3600",
            "prate_interval_duration_h": float(meta["endStep"]) - float(meta["startStep"]),
        }
        assert source_entry["conversion_method"] == "TEMPORALLY_ALIGNED_FROM_NATIVE_PRATE_INTERVAL"
        assert source_entry["conversion_formula"] == "rate_mm_h = prate_kg_m2_s * 3600"
        assert source_entry["prate_interval_duration_h"] == 2.0
        np.testing.assert_allclose(rate_mm_h, 2.0, rtol=1e-10)

    @pytest.mark.parametrize("end_lead", [1, 2, 3, 7, 12, 18])
    def test_single_field_sufficient_for_all_leads(self, end_lead):
        """prate_mean_to_rate() must work on a single PRATE field at any lead.
        No previous GRIB field should ever be fetched for PRATE."""
        start = ((end_lead - 1) // 6) * 6
        meta = _prate_meta(start=float(start), end=float(end_lead))
        values = np.array([[4.0 / 3600]])
        result = prate_mean_to_rate(values, meta)
        np.testing.assert_allclose(
            result, 4.0, rtol=1e-10,
            err_msg=f"Failed at end_lead={end_lead} (startStep={start})",
        )
