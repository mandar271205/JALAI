"""Fail-closed final benchmark records across scientific dimensions."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from typing import Any


class MetricStatus(str, enum.Enum):
    EVALUATED = "EVALUATED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass(frozen=True)
class BenchmarkMetric:
    dimension: str
    model_id: str
    metric: str
    status: MetricStatus
    value: float | None
    units: str | None
    reason: str | None
    independent_blocks: int | None = None

    def validate(self) -> None:
        if self.status is MetricStatus.NOT_EVALUABLE and self.value is not None:
            raise ValueError("Unsupported metrics must not receive fabricated zero/value")
        if self.status is MetricStatus.EVALUATED and self.value is None:
            raise ValueError("Evaluated metrics require a value")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        row = asdict(self)
        row["status"] = self.status.value
        return row


METRICS = {
    "rainfall": (
        "MAE",
        "RMSE",
        "Bias",
        "CSI",
        "POD",
        "FAR",
        "F1",
        "Brier",
        "reliability",
        "runtime",
        "memory",
    ),
    "flood_physics": (
        "depth_MAE",
        "depth_RMSE",
        "extent_IoU",
        "extent_F1",
        "volume_error",
        "mass_balance",
        "solver_runtime",
    ),
    "fno": (
        "target_MAE",
        "inference_runtime",
        "speedup_ratio",
        "error_by_depth_regime",
        "wet_dry_F1",
    ),
    "risk": ("calibration", "tier_consistency", "uncertainty_coverage", "event_aggregation"),
    "citizen": (
        "precision",
        "recall",
        "F1",
        "false_corroboration",
        "spam_rejection",
        "calibration",
    ),
}


def benchmark_skeleton(model_by_dimension: dict[str, str]) -> list[BenchmarkMetric]:
    output: list[BenchmarkMetric] = []
    for dimension, metrics in METRICS.items():
        for metric in metrics:
            output.append(
                BenchmarkMetric(
                    dimension,
                    model_by_dimension.get(dimension, "UNAVAILABLE"),
                    metric,
                    MetricStatus.NOT_EVALUABLE,
                    None,
                    None,
                    "required genuine reference/evaluation absent",
                )
            )
    return output


def assemble_benchmark(
    provided: list[BenchmarkMetric],
    model_by_dimension: dict[str, str] | None = None,
) -> list[BenchmarkMetric]:
    """Merge explicit evaluated metrics into a fail-closed complete matrix."""
    allowed = {(dimension, metric) for dimension, metrics in METRICS.items() for metric in metrics}
    indexed: dict[tuple[str, str], BenchmarkMetric] = {}
    for item in provided:
        item.validate()
        key = (item.dimension, item.metric)
        if key not in allowed:
            raise ValueError(f"Unknown benchmark metric {key}")
        if key in indexed:
            raise ValueError(f"Duplicate benchmark metric {key}")
        indexed[key] = item
    return [
        indexed.get((item.dimension, item.metric), item)
        for item in benchmark_skeleton(model_by_dimension or {})
    ]
