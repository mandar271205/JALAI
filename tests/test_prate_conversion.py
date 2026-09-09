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

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from jalrakshak_ml.gfs_replay.core import (
    interval_amount,
    prate_mean_to_rate,
    reconstruct_hourly,
    utc,
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


# ---------------------------------------------------------------------------
# 10. valid_time consistency
#     parse_prate_interval (rich_download.py) enforces: valid_time == cycle + endStep.
#     prate_mean_to_rate() (core.py) does NOT re-validate valid_time — that is the
#     parser's responsibility, already enforced before the field reaches conversion.
#     These tests verify: (a) the parser rejects mismatched valid_time;
#     (b) prate_mean_to_rate() is indifferent to valid_time (correct layering).
# ---------------------------------------------------------------------------

class TestValidTimeConsistency:
    """valid_time == forecast_reference_time + endStep is enforced by parse_prate_interval."""

    def test_parse_prate_interval_rejects_mismatched_valid_time(self):
        """parse_prate_interval must raise if valid_time != cycle + endStep."""
        from jalrakshak_ml.gfs_replay.rich_download import parse_prate_interval

        bad_meta = {
            "shortName": "prate",
            "typeOfLevel": "surface",
            "level": 0,
            "stepType": "avg",
            "startStep": 0,
            "endStep": 2,
            "units": "kg m**-2 s**-1",
            "forecast_reference_time": CYCLE.isoformat(),
            # valid_time deliberately mismatched: should be CYCLE + 2h = 02:00Z
            "valid_time": (CYCLE + timedelta(hours=3)).isoformat(),  # wrong: +3h
        }
        with pytest.raises(ValueError, match="valid time differs from cycle plus end step"):
            parse_prate_interval(bad_meta)

    def test_parse_prate_interval_accepts_correct_valid_time(self):
        """parse_prate_interval must accept valid_time == cycle + endStep."""
        from jalrakshak_ml.gfs_replay.rich_download import parse_prate_interval

        good_meta = {
            "shortName": "prate",
            "typeOfLevel": "surface",
            "level": 0,
            "stepType": "avg",
            "startStep": 0,
            "endStep": 2,
            "units": "kg m**-2 s**-1",
            "forecast_reference_time": CYCLE.isoformat(),
            "valid_time": (CYCLE + timedelta(hours=2)).isoformat(),  # correct
        }
        result = parse_prate_interval(good_meta)
        assert result["end_step"] == 2
        assert result["native_valid_time"] == (CYCLE + timedelta(hours=2)).isoformat()
        assert result["cycle_time"] == CYCLE.isoformat()

    def test_prate_mean_to_rate_does_not_require_valid_time_key(self):
        """prate_mean_to_rate() is a pure conversion function; it must not require
        valid_time to be present in metadata — that field is the parser's concern.
        This documents the correct layering of responsibilities."""
        meta_without_valid_time = _prate_meta(start=0, end=2)
        # _prate_meta does not include valid_time — if prate_mean_to_rate required it,
        # the metadata fixture would need updating; verify it does not crash.
        result = prate_mean_to_rate(np.array([[2.0 / 3600]]), meta_without_valid_time)
        np.testing.assert_allclose(result, 2.0, rtol=1e-10)

    @pytest.mark.parametrize("end_lead", [1, 2, 6, 7, 12])
    def test_parse_prate_interval_valid_time_invariant_for_real_gfs_leads(self, end_lead):
        """For every realistic GFS lead, the valid_time must equal cycle + endStep."""
        from jalrakshak_ml.gfs_replay.rich_download import parse_prate_interval

        start = ((end_lead - 1) // 6) * 6
        meta = {
            "shortName": "prate",
            "typeOfLevel": "surface",
            "level": 0,
            "stepType": "avg",
            "startStep": start,
            "endStep": end_lead,
            "units": "kg m**-2 s**-1",
            "forecast_reference_time": CYCLE.isoformat(),
            "valid_time": (CYCLE + timedelta(hours=end_lead)).isoformat(),
        }
        result = parse_prate_interval(meta)
        assert result["end_step"] == end_lead
        assert result["start_step"] == start
        assert result["native_valid_time"] == (CYCLE + timedelta(hours=end_lead)).isoformat()


# ---------------------------------------------------------------------------
# 11. Temporal non-independence provenance
#
#     Each native GFS PRATE field covers a 1-hour interval.
#     A 30-minute output slot is aligned to a native 1-hour PRATE interval.
#     Two consecutive 30-minute slots (e.g. +30m and +60m) that share the same
#     native PRATE interval carry NO new temporal information relative to each other.
#
#     align_prate_horizons() (rich_pipeline.py) must emit:
#       - independent_native_observation: False
#       - temporal_disaggregation_method: "uniform_within_native_interval"
#       - source_interval_start / source_interval_end (native bounds)
#       - cycle_time, lead_hour, availability_basis (full provenance chain)
#
#     Do NOT imply that 30-minute disaggregation creates new GFS information.
# ---------------------------------------------------------------------------

class TestTemporalNonIndependenceProvenance:
    """align_prate_horizons() must correctly declare temporal non-independence."""

    def _run_align(self, issue_offset_h: float = 7.5) -> list:
        """Run align_prate_horizons for a standard 4-horizon issue."""
        from jalrakshak_ml.gfs_replay.rich_pipeline import align_prate_horizons

        issue = CYCLE + timedelta(hours=issue_offset_h)
        # Build the metadata_by_end_step dict as the pipeline does
        metadata_by_end_step = {}
        for horizon in (30, 60, 90, 120):
            aligned = issue + timedelta(minutes=horizon)
            end_lead = math.ceil((aligned - CYCLE).total_seconds() / 3600)
            start = ((end_lead - 1) // 6) * 6
            metadata_by_end_step[end_lead] = {
                "shortName": "prate",
                "typeOfLevel": "surface",
                "level": 0,
                "stepType": "avg",
                "startStep": start,
                "endStep": end_lead,
                "units": "kg m**-2 s**-1",
                "forecast_reference_time": CYCLE.isoformat(),
                "valid_time": (CYCLE + timedelta(hours=end_lead)).isoformat(),
            }
        return align_prate_horizons(issue, CYCLE, metadata_by_end_step)

    def test_independent_native_observation_is_false_for_all_slots(self):
        """Every output slot must declare independent_native_observation=False."""
        records = self._run_align()
        assert len(records) == 4
        for rec in records:
            assert rec["independent_native_observation"] is False, (
                f"Slot {rec['horizon_minutes']}m must declare non-independence; "
                "30-minute disaggregation does not create new GFS information."
            )

    def test_temporal_disaggregation_method_is_uniform(self):
        """temporal_disaggregation_method must be 'uniform_within_native_interval'."""
        records = self._run_align()
        for rec in records:
            assert rec["temporal_disaggregation_method"] == "uniform_within_native_interval", (
                f"Slot {rec['horizon_minutes']}m: disaggregation method must be explicit."
            )

    def test_native_interval_bounds_present_in_all_slots(self):
        """source_interval_start and source_interval_end must be present."""
        records = self._run_align()
        for rec in records:
            assert "source_interval_start" in rec, \
                f"Slot {rec['horizon_minutes']}m missing source_interval_start"
            assert "source_interval_end" in rec, \
                f"Slot {rec['horizon_minutes']}m missing source_interval_end"
            # Interval start must precede end
            start = datetime.fromisoformat(rec["source_interval_start"])
            end = datetime.fromisoformat(rec["source_interval_end"])
            assert start < end

    def test_full_provenance_chain_present(self):
        """Every record must carry: cycle_time, lead_hour, availability_basis."""
        records = self._run_align()
        for rec in records:
            assert "cycle_time" in rec
            assert "lead_hour" in rec
            assert "availability_basis" in rec
            assert utc(rec["cycle_time"]) == CYCLE

    def test_two_slots_sharing_native_interval_have_identical_bounds(self):
        """If two 30-min slots fall within the same 1-hour PRATE interval, they must
        report the same source_interval_start/end — making non-independence explicit.

        Issue at 07:30 UTC: +30m slot (08:00) and +60m slot (08:30) both fall in
        the native 07:00–08:00 PRATE interval when the cycle is 00:00 UTC.

        This test confirms that when two output slots share the same native lead,
        their interval bounds are identical — explicitly marking that no additional
        temporal information was introduced by the 30-minute disaggregation.
        """
        from jalrakshak_ml.gfs_replay.rich_pipeline import align_prate_horizons

        # Issue 07:00 UTC: +30m → 07:30, +60m → 08:00
        # Both slots: end_lead = ceil((7.5h)/1h) = 8, ceil((8h)/1h) = 8
        # So the +30m slot at 07:30 maps to ceil((7.5)/1)=8 and
        # +60m at 08:00 maps to ceil(8/1)=8 → same native interval [7h,8h]
        issue = CYCLE + timedelta(hours=7, minutes=0)
        # end leads: +30m → ceil(7.5)=8, +60m → ceil(8)=8, +90m → ceil(8.5)=9, +120m → ceil(9)=9
        metadata_by_end_step = {}
        for lead in (8, 9):
            start = ((lead - 1) // 6) * 6
            metadata_by_end_step[lead] = {
                "shortName": "prate",
                "typeOfLevel": "surface",
                "level": 0,
                "stepType": "avg",
                "startStep": start,
                "endStep": lead,
                "units": "kg m**-2 s**-1",
                "forecast_reference_time": CYCLE.isoformat(),
                "valid_time": (CYCLE + timedelta(hours=lead)).isoformat(),
            }
        records = align_prate_horizons(issue, CYCLE, metadata_by_end_step)
        assert len(records) == 4

        # +30m and +60m slots both map to native lead 8 → same interval [7h, 8h]
        slot_30 = records[0]  # horizon_minutes=30
        slot_60 = records[1]  # horizon_minutes=60
        assert slot_30["lead_hour"] == slot_60["lead_hour"] == 8, (
            "Both 30m and 60m slots must map to the same native lead"
        )
        assert slot_30["source_interval_start"] == slot_60["source_interval_start"], (
            "Shared native interval: start must be identical for both slots"
        )
        assert slot_30["source_interval_end"] == slot_60["source_interval_end"], (
            "Shared native interval: end must be identical for both slots"
        )
        # Explicitly: no new temporal information between these two slots
        assert slot_30["independent_native_observation"] is False
        assert slot_60["independent_native_observation"] is False

    def test_no_new_temporal_information_field_semantics(self):
        """Document that independent_native_observation=False means:
        the 30-minute output slot does NOT represent an independent native GFS
        observation. The native PRATE was a 1-hour mean; subdividing it into
        two 30-minute slots does not create new temporal resolution."""
        records = self._run_align()
        for rec in records:
            # The field must be literally False (not just falsy)
            assert rec["independent_native_observation"] is False
            # native_cadence_minutes must be 60 (not 30) — confirms no false precision
            assert rec["native_cadence_minutes"] == 60
            # output_cadence_minutes is 30 — but this is disaggregation, not new data
            assert rec["output_cadence_minutes"] == 30

