"""Forecast-vintage selection, precipitation intervals, and conservative allocation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

LOCKED_EVENTS = (
    "mumbai_monsoon_2023_08_24",
    "mumbai_monsoon_2024_08_04",
    "mumbai_monsoon_2024_09_05",
)
NON_TEST_EVENTS = (
    "mumbai_monsoon_2023_07_18",
    "mumbai_monsoon_2023_07_25",
)
ALL_SUPPORTED_EVENTS = LOCKED_EVENTS + NON_TEST_EVENTS
METHOD = "uniform_within_native_interval"


def utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("An explicit UTC offset is required")
    return parsed.astimezone(UTC)


def source_uri(cycle: datetime, lead: int) -> str:
    cycle = utc(cycle)
    return (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
        f"gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos/gfs.t{cycle:%H}z.pgrb2.0p25.f{lead:03d}"
    )


@dataclass(frozen=True)
class Selection:
    issue_time: datetime
    cycle_time: datetime
    availability_time: datetime
    availability_basis: str
    forecast_hours: tuple[int, ...]
    required_horizon_minutes: int

    def validate(self) -> None:
        issue, cycle, available = map(
            utc, (self.issue_time, self.cycle_time, self.availability_time)
        )
        if cycle.hour % 6 or cycle.minute or cycle.second or cycle.microsecond:
            raise ValueError("Invalid GFS cycle time")
        if not cycle <= available <= issue:
            raise ValueError("Unavailable or later cycle: temporal leakage")
        if (
            not self.forecast_hours
            or tuple(sorted(set(self.forecast_hours))) != self.forecast_hours
        ):
            raise ValueError("Missing or duplicate cycle/lead")
        last = math.ceil(
            (issue - cycle).total_seconds() / 3600 + self.required_horizon_minutes / 60
        )
        if self.forecast_hours != tuple(range(1, last + 1)) or last > 120:
            raise ValueError("Incomplete native hourly forecast coverage")


def select_gfs_forecast_as_of(
    issue_time: str | datetime,
    required_horizon_minutes: int,
    *,
    latency_hours: float = 6.0,
    known_availability: dict[str, str] | None = None,
) -> Selection:
    """Select one vintage available as of issue, under an explicit latency assumption.

    Known times, when supplied, refer to availability of the entire required lead
    bundle. Unknown cycles are ineligible in known-time mode. No later-cycle fallback.
    Fetch from f001 to reconstruct accumulated means including their origin.
    """
    issue = utc(issue_time)
    if issue.minute not in (0, 30) or issue.second or issue.microsecond:
        raise ValueError("Issue time must be on the locked half-hour schedule")
    if required_horizon_minutes not in (30, 60, 90, 120):
        raise ValueError("Required horizon must be 30, 60, 90, or 120 minutes")
    if not math.isfinite(latency_hours) or latency_hours < 6:
        raise ValueError("Assumed latency must be at least six hours")
    if known_availability is None:
        cutoff = issue - timedelta(hours=latency_hours)
        cycle = cutoff.replace(hour=(cutoff.hour // 6) * 6, minute=0, second=0, microsecond=0)
        available = cycle + timedelta(hours=latency_hours)
        basis = f"assumed_cycle_plus_{latency_hours:g}h_required_bundle; not_observed_publication"
    else:
        candidates = []
        for cycle_value, available_value in known_availability.items():
            c, a = utc(cycle_value), utc(available_value)
            if a < c:
                raise ValueError("Availability cannot precede initialization")
            if c <= a <= issue:
                candidates.append((c, a))
        if not candidates:
            raise ValueError("No known available forecast cycle at issue time")
        cycle, available = max(candidates)
        basis = "known_required_bundle_availability"
    end_hour = math.ceil((issue - cycle).total_seconds() / 3600 + required_horizon_minutes / 60)
    result = Selection(
        issue, cycle, available, basis, tuple(range(1, end_hour + 1)), required_horizon_minutes
    )
    result.validate()
    return result


def finite_rain(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if not np.isfinite(arr).all():
        raise ValueError("Non-finite rainfall or insufficient spatial coverage")
    if np.any(arr < 0):
        raise ValueError("Negative rainfall / accumulation reset error: non-negative values required")
    return arr


def interval_amount(values: np.ndarray, metadata: dict) -> np.ndarray:
    """Convert exactly identified APCP or interval-mean PRATE into interval mm."""
    start, end = float(metadata["startStep"]), float(metadata["endStep"])
    if metadata["stepUnits"] != "h" or not 0 <= start < end:
        raise ValueError("Invalid or zero-duration accumulation interval")
    units = metadata["units"].replace(" ", "")
    arr = finite_rain(values)
    field = (
        metadata["shortName"],
        metadata["stepType"],
        metadata["typeOfLevel"],
        metadata["level"],
    )
    if field == ("tp", "accum", "surface", 0):
        if units not in ("kgm**-2", "kgm^-2", "kg/m^2", "mm"):
            raise ValueError(f"Unsupported APCP units: {units}")
        return arr
    if field == ("prate", "avg", "surface", 0):
        if units not in ("kgm**-2s**-1", "kgm^-2s^-1", "kg/m^2/s"):
            raise ValueError(f"Unsupported PRATE units: {units}")
        return arr * 3600 * (end - start)
    raise ValueError("Wrong precipitation variable or statistical semantics")


@dataclass
class HourlyInterval:
    start: datetime
    end: datetime
    rate: np.ndarray
    sources: list[dict]
    conversion_method: str
    qc_flags: list[str]


def reconstruct_hourly(fields: list[tuple[np.ndarray, dict]]) -> list[HourlyInterval]:
    """Unroll accumulated amounts/means; never difference across origins or cycles."""
    if not fields:
        raise ValueError("No precipitation fields")
    ordered = sorted(fields, key=lambda pair: float(pair[1]["endStep"]))
    previous = None
    seen = set()
    output = []
    for values, meta in ordered:
        cycle = utc(meta["forecast_reference_time"])
        start, end = float(meta["startStep"]), float(meta["endStep"])
        if not start.is_integer() or not end.is_integer():
            raise ValueError("Native GFS intervals must have integer hourly steps")
        key = (cycle, end)
        if key in seen:
            raise ValueError("Duplicate cycle/lead")
        seen.add(key)
        if utc(meta["valid_time"]) != cycle + timedelta(hours=end):
            raise ValueError("GRIB valid time differs from cycle plus lead")
        amount = interval_amount(values, meta)
        sources = [meta]
        flags = []
        hourly_start = start
        if previous is not None:
            prev_amount, prev_meta = previous
            if cycle != utc(prev_meta["forecast_reference_time"]):
                raise ValueError("Cannot difference or combine different forecast cycles")
            if (meta["shortName"], meta["stepType"], meta["units"]) != (
                prev_meta["shortName"],
                prev_meta["stepType"],
                prev_meta["units"],
            ) or amount.shape != prev_amount.shape:
                raise ValueError("Inconsistent precipitation product/grid")
            previous_end = float(prev_meta["endStep"])
            if end != previous_end + 1:
                raise ValueError("Missing native hourly interval")
            if start == float(prev_meta["startStep"]):
                delta = amount - prev_amount
                # ecCodes packing can cause tiny cancellation error; never hide real resets.
                if np.any(delta < -1e-5):
                    raise ValueError("Negative increment / accumulation reset error")
                if np.any(delta < 0):
                    flags.append("ROUNDING_NEGATIVE_INCREMENT_CLAMPED_LT_1E_5_MM")
                hourly_amount = np.maximum(delta, 0)
                hourly_start = previous_end
                sources = [prev_meta, meta]
            elif start == previous_end:
                hourly_amount = amount
                flags.append("EXPLICIT_ACCUMULATION_ORIGIN_RESET")
            else:
                raise ValueError("Accumulation origin reset overlaps or skips an interval")
        else:
            hourly_amount = amount
        if end - hourly_start != 1:
            raise ValueError("Cannot infer hourly amount without the preceding accumulation")
        method = "APCP_mm" if meta["shortName"] == "tp" else "PRATE_x3600_x_duration_hours"
        if len(sources) == 2:
            method += "; difference_same_cycle_same_origin"
        output.append(
            HourlyInterval(
                cycle + timedelta(hours=hourly_start),
                cycle + timedelta(hours=end),
                finite_rain(hourly_amount),
                sources,
                method + "; divide_by_1h",
                flags,
            )
        )
        previous = amount, meta
    return output


def allocate_half_hours(
    intervals: list[HourlyInterval], selection: Selection
) -> tuple[np.ndarray, list]:
    """Time-overlap integration; each output is a mean rate over the preceding 30 min."""
    selection.validate()
    ordered = sorted(intervals, key=lambda item: item.start)
    if not ordered:
        raise ValueError("Missing output interval")
    for index, item in enumerate(ordered):
        if item.end - item.start != timedelta(hours=1):
            raise ValueError("Not a native hourly interval")
        if index and item.start < ordered[index - 1].end:
            raise ValueError("Duplicate or overlapping native intervals")
        for meta in item.sources:
            if utc(meta["forecast_reference_time"]) != selection.cycle_time:
                raise ValueError("Later/different-cycle leakage")
        finite_rain(item.rate)
    rates, windows = [], []
    for horizon in range(30, selection.required_horizon_minutes + 1, 30):
        end = selection.issue_time + timedelta(minutes=horizon)
        start = end - timedelta(minutes=30)
        amount = np.zeros_like(ordered[0].rate, dtype=np.float64)
        seconds = 0.0
        contributors = []
        for item in ordered:
            overlap = max(0.0, (min(end, item.end) - max(start, item.start)).total_seconds())
            if overlap:
                amount += item.rate * overlap / 3600
                seconds += overlap
                contributors.append(
                    {
                        "native_interval_start": item.start.isoformat(),
                        "native_interval_end": item.end.isoformat(),
                        "overlap_minutes": overlap / 60,
                        "conversion_method": item.conversion_method,
                        "source_variable_metadata": item.sources,
                        "qc_flags": item.qc_flags,
                    }
                )
        if seconds != 1800:
            raise ValueError("Missing output interval: incomplete native coverage")
        rates.append(finite_rain(amount / 0.5))
        windows.append(
            {
                "output_interval_start": start.isoformat(),
                "output_valid_time": end.isoformat(),
                "horizon_minutes": horizon,
                "forecast_lead_hours": (end - selection.cycle_time).total_seconds() / 3600,
                "native_intervals": contributors,
            }
        )
    return np.stack(rates), windows
