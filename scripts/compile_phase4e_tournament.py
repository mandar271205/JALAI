"""Compile a paired common-sample Phase 4E validation tournament."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from jalrakshak_ml.deep_nowcast.final_contracts import SEEDS
from jalrakshak_ml.deep_nowcast.final_evaluation import (
    evaluate_validation_events,
    paired_event_bootstrap,
)
from jalrakshak_ml.deep_nowcast.final_tournament import REQUIRED_MODELS
from jalrakshak_ml.deep_nowcast.phase4e_runner import event_block_bootstrap
from jalrakshak_ml.deep_nowcast.splits import VALIDATION_EVENTS_AUTHORITATIVE

DEEP_MODELS = {"convlstm_v3", "unet_convgru_v1", "st_attention_nowcaster_v1"}
REFERENCE_MODELS = {"persistence", "pysteps"}


def _event_mae(metrics: dict) -> dict[str, float]:
    return {
        event_id: float(
            np.mean([horizon["continuous"]["mae"] for horizon in report["horizons"].values()])
        )
        for event_id, report in metrics["per_event"].items()
    }


def _flatten_scores(value, prefix="") -> dict[str, float]:
    output: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in {"mae", "rmse", "bias", "pod", "far", "csi", "f1"} and isinstance(
                child, (int, float)
            ):
                output[path] = float(child)
            else:
                output.update(_flatten_scores(child, path))
    return output


def _aggregate_seed_reports(seed_reports: dict[int, dict]) -> dict:
    flattened = {seed: _flatten_scores(report) for seed, report in seed_reports.items()}
    common = set.intersection(*(set(report) for report in flattened.values()))
    aggregate = {}
    for metric in sorted(common):
        values = np.asarray([flattened[seed][metric] for seed in SEEDS], dtype=float)
        if np.isfinite(values).all():
            aggregate[metric] = {
                "mean": float(values.mean()),
                "standard_deviation": float(values.std(ddof=1)),
            }
    return {
        "individual_seed_reports": {str(seed): seed_reports[seed] for seed in SEEDS},
        "aggregate_metrics": aggregate,
        "independence_unit": "seed_run; event identity retained in every seed report",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifests = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.manifest]
    if any(manifest.get("input_policy") != "full_inputs" for manifest in manifests):
        raise ValueError("The main tournament accepts only full-input prediction manifests")
    by_key = {}
    for manifest in manifests:
        model = manifest["model"]
        key = (model, int(manifest["seed"]) if model in DEEP_MODELS else None)
        if key in by_key:
            raise ValueError(f"Duplicate tournament contender: {key}")
        by_key[key] = manifest
    present_models = {key[0] for key in by_key}
    if not REQUIRED_MODELS.issubset(present_models):
        raise ValueError(
            f"Missing required tournament models: {sorted(REQUIRED_MODELS - present_models)}"
        )
    if any((model, None) not in by_key for model in REFERENCE_MODELS):
        raise ValueError("Persistence and PySTEPS each require one reference manifest")
    for model in DEEP_MODELS:
        model_seeds = {seed for name, seed in by_key if name == model}
        if model_seeds != set(SEEDS):
            raise ValueError(f"{model} requires exactly seeds {SEEDS}")

    reference_targets: dict[str, np.ndarray] = {}
    reference_masks: dict[str, np.ndarray] = {}
    reference_sample_ids: list[str] | None = None
    report = {
        "contenders": {},
        "deep_architecture_aggregates": {},
        "paired_comparisons_vs_persistence": {},
        "paired_common_samples": True,
        "bootstrap_unit": "event",
        "locked_test_accessed": False,
    }
    for (model_name, seed), manifest in sorted(by_key.items(), key=lambda item: str(item[0])):
        if manifest.get("split") != "validation" or manifest.get("locked_test_accessed"):
            raise PermissionError("Tournament accepts uncontaminated validation manifests only")
        if manifest.get("sample_count") != 51 or len(manifest.get("sample_ids", [])) != 51:
            raise ValueError("Every contender must contain exactly 51 validation samples")
        if len(set(manifest["sample_ids"])) != 51:
            raise ValueError("Validation sample identities must be unique")
        if reference_sample_ids is None:
            reference_sample_ids = manifest["sample_ids"]
        elif manifest["sample_ids"] != reference_sample_ids:
            raise ValueError("Contenders do not share identical ordered validation samples")
        if {record["event_id"] for record in manifest.get("events", [])} != set(
            VALIDATION_EVENTS_AUTHORITATIVE
        ):
            raise ValueError("Manifest does not contain the exact validation event set")
        event_data = {}
        for record in manifest["events"]:
            with np.load(record["artifact"], allow_pickle=False) as arrays:
                prediction = arrays["prediction_mm_h"]
                target = arrays["target_mm_h"]
                mask = arrays["valid_mask"]
            event_id = record["event_id"]
            if event_id in reference_targets:
                if not np.array_equal(target, reference_targets[event_id], equal_nan=True):
                    raise ValueError("Models do not share identical validation targets")
                if not np.array_equal(mask, reference_masks[event_id]):
                    raise ValueError("Models do not share identical validation masks")
            else:
                reference_targets[event_id] = target
                reference_masks[event_id] = mask
            event_data[event_id] = (prediction, target, mask)
        metrics = evaluate_validation_events(event_data)
        mae_blocks = {
            event_id: [values["horizons"]["30"]["continuous"]["mae"]]
            for event_id, values in metrics["per_event"].items()
        }
        metrics["event_bootstrap_mae"] = event_block_bootstrap(mae_blocks)
        contender = model_name if seed is None else f"{model_name}:seed_{seed}"
        report["contenders"][contender] = metrics
    persistence_scores = _event_mae(report["contenders"]["persistence"])
    for contender, metrics in report["contenders"].items():
        if contender == "persistence":
            continue
        report["paired_comparisons_vs_persistence"][contender] = paired_event_bootstrap(
            _event_mae(metrics), persistence_scores
        )
    for model in sorted(DEEP_MODELS):
        report["deep_architecture_aggregates"][model] = _aggregate_seed_reports(
            {seed: report["contenders"][f"{model}:seed_{seed}"] for seed in SEEDS}
        )
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    part.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(destination)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
