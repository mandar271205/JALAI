"""Authoritative Phase 4E split definitions and verification for JalRakshak AI.

Authoritative event partition:
- 12 TRAIN events
- 3 VALIDATION events
- 3 LOCKED TEST events
Total: 18 independent synoptic events.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import Any

from jalrakshak_ml.deep_nowcast.dataset import SequenceIndex

TRAIN_EVENTS_AUTHORITATIVE: tuple[str, ...] = (
    "mumbai_monsoon_2021_06_18",
    "mumbai_monsoon_2021_07_16",
    "mumbai_monsoon_2021_08_08",
    "mumbai_monsoon_2021_09_07",
    "mumbai_monsoon_2022_06_22",
    "mumbai_monsoon_2022_07_05",
    "mumbai_monsoon_2022_07_14",
    "mumbai_monsoon_2022_08_09",
    "mumbai_monsoon_2023_06_28",
    "mumbai_monsoon_2023_07_18",
    "mumbai_monsoon_2023_08_08",
    "mumbai_monsoon_2023_09_07",
)

VALIDATION_EVENTS_AUTHORITATIVE: tuple[str, ...] = (
    "mumbai_monsoon_2023_07_25",
    "mumbai_monsoon_2024_07_08",
    "mumbai_monsoon_2024_07_21",
)

LOCKED_TEST_EVENTS_AUTHORITATIVE: tuple[str, ...] = (
    "mumbai_monsoon_2023_08_24",
    "mumbai_monsoon_2024_08_04",
    "mumbai_monsoon_2024_09_05",
)

ALL_18_EVENTS: tuple[str, ...] = (
    TRAIN_EVENTS_AUTHORITATIVE
    + VALIDATION_EVENTS_AUTHORITATIVE
    + LOCKED_TEST_EVENTS_AUTHORITATIVE
)


@dataclass(frozen=True, slots=True)
class ResearchSplits:
    """Immutable encapsulation of the Phase 4E research partitions."""

    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]

    def __post_init__(self) -> None:
        train_set = set(self.train)
        val_set = set(self.validation)
        test_set = set(self.test)

        if len(train_set.intersection(val_set)) > 0:
            raise ValueError(f"Train and Validation overlap: {train_set.intersection(val_set)}")
        if len(train_set.intersection(test_set)) > 0:
            raise ValueError(f"Train and Test overlap: {train_set.intersection(test_set)}")
        if len(val_set.intersection(test_set)) > 0:
            raise ValueError(f"Validation and Test overlap: {val_set.intersection(test_set)}")

        # Ensure locked test events are identical
        if set(self.test) != set(LOCKED_TEST_EVENTS_AUTHORITATIVE):
            raise ValueError(
                f"Locked test events mismatch! Expected {LOCKED_TEST_EVENTS_AUTHORITATIVE}, got {self.test}"
            )

    @property
    def non_test_events(self) -> tuple[str, ...]:
        return self.train + self.validation

    def get_split(self, event_id: str) -> str:
        if event_id in self.train:
            return "train"
        if event_id in self.validation:
            return "validation"
        if event_id in self.test:
            return "test"
        raise KeyError(f"Event ID {event_id!r} not in authoritative splits.")


def get_authoritative_splits(catalog_path: Path | str | None = None) -> ResearchSplits:
    """Return the authoritative ResearchSplits, verifying against catalog if provided."""
    splits = ResearchSplits(
        train=TRAIN_EVENTS_AUTHORITATIVE,
        validation=VALIDATION_EVENTS_AUTHORITATIVE,
        test=LOCKED_TEST_EVENTS_AUTHORITATIVE,
    )
    if catalog_path is not None:
        p = Path(catalog_path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            cat_splits = data.get("research_splits_locked", {})
            cat_test = set(cat_splits.get("test", []))
            if cat_test and cat_test != set(LOCKED_TEST_EVENTS_AUTHORITATIVE):
                raise ValueError("Catalog test events disagree with authoritative locked test specification")
    return splits


def is_locked_test_event(event_id: str) -> bool:
    """Return True if event_id is one of the permanently locked test events."""
    return event_id in LOCKED_TEST_EVENTS_AUTHORITATIVE


def build_event_sequences(
    event_id: str,
    times: Sequence[str] | None = None,
    start_time: str | datetime | None = None,
    expected_frames: int = 24,
    history_length: int = 4,
    prediction_horizon: int = 4,
    temporal_step_minutes: int = 30,
    event_path: str = "",
) -> list[SequenceIndex]:
    """Authoritative sequence builder shared between dataset loading and GFS replay planning.

    Enforces the exact nowcasting sample contract:
      - history_length contiguous frames spaced by temporal_step_minutes (default 4)
      - prediction_horizon contiguous future target frames spaced by temporal_step_minutes (default 4)
      - window = history_length + prediction_horizon (default 4 + 4 = 8 frames)
      - issue_time = input_times[-1] (latest history observation)
      - target_times = future target valid times (issue_time + 30, +60, +90, +120 min)

    For an event of N frames (default 24):
      Valid sequences = N - (history_length + prediction_horizon) + 1
      For 24 frames: 24 - 8 + 1 = 17 sequences.
    """
    if times is None:
        if start_time is None:
            raise ValueError(f"Either 'times' or 'start_time' must be provided for event {event_id!r}")
        if isinstance(start_time, str):
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        else:
            dt = start_time
        frame_dts = [
            dt + timedelta(minutes=i * temporal_step_minutes)
            for i in range(expected_frames)
        ]
        times = [t.isoformat() for t in frame_dts]
    else:
        times = [str(t) for t in times]

    window = history_length + prediction_horizon
    indices: list[SequenceIndex] = []

    for start in range(len(times) - window + 1):
        candidate = times[start : start + window]
        cand_dts = [datetime.fromisoformat(str(t).replace("Z", "+00:00")) for t in candidate]
        deltas = [
            (right - left).total_seconds() / 60.0
            for left, right in pairwise(cand_dts)
        ]
        if any(delta != temporal_step_minutes for delta in deltas):
            continue

        indices.append(
            SequenceIndex(
                event_id=event_id,
                event_path=event_path,
                start_index=start,
                input_times=tuple(candidate[:history_length]),
                target_times=tuple(candidate[history_length:]),
            )
        )

    return indices
