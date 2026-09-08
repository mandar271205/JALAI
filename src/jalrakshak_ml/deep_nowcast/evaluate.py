"""Mask-aware held-out evaluation shared by all nowcast providers."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.dataset import build_datasets_from_config
from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
from jalrakshak_ml.deep_nowcast.verification import json_safe, pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


def evaluate_heldout(
    dataset,
    convlstm: ConvLSTMInference,
    *,
    thresholds: list[float] | None = None,
    max_samples: int | None = None,
) -> dict[str, Any]:
    """Evaluate all providers over the identical target-mask/finiteness intersection."""
    if dataset.split != "test":
        raise ValueError("Official held-out evaluation requires the test split")
    thresholds = thresholds or [0.1, 1.0, 5.0]
    evaluator = NowcastEvaluator(thresholds=thresholds)
    persistence = PersistenceNowcast()
    pysteps = PystepsNowcast()
    rows: dict[str, list[list[dict[str, Any]]]] = {
        "persistence": [],
        "pysteps": [],
        "convlstm": [],
    }
    used_events: list[str] = []
    requested_target_pixels = 0
    common_valid_pixels = 0
    sample_count = min(len(dataset), max_samples) if max_samples else len(dataset)
    for index in range(sample_count):
        raw = dataset.get_raw(index)
        history = raw["inputs"]
        rainfall_history = history[:, dataset.input_channels.index("rainfall")]
        observation = raw["target"][:, 0]
        target_mask = raw["target_mask"][:, 0].astype(bool) & np.isfinite(observation)
        lead_times = observation.shape[0]
        predictions = {
            "persistence": persistence.predict(rainfall_history[-1], lead_times),
            "pysteps": pysteps.predict(rainfall_history, lead_times),
            "convlstm": convlstm.predict(history, lead_times),
        }
        common_mask = target_mask.copy()
        for prediction in predictions.values():
            common_mask &= np.isfinite(prediction)
        requested_target_pixels += int(target_mask.sum())
        common_valid_pixels += int(common_mask.sum())
        for name, prediction in predictions.items():
            frame = evaluator.evaluate_sequence(
                observation,
                prediction,
                valid_mask=common_mask,
            )
            rows[name].append(frame.to_dict(orient="records"))
        used_events.append(raw["metadata"]["event_id"])

    providers = {}
    for name, sample_rows in rows.items():
        pooled = pool_metric_rows(sample_rows, thresholds)
        providers[name] = {
            "overall": pooled["overall"],
            "metrics": pooled["by_lead"],
        }
    providers["pysteps"].update({
        "available": bool(pysteps._is_available),
        "fallback_to_persistence": bool(not pysteps._is_available and pysteps.fallback),
    })
    report = {
        "status": "COMPLETED",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_version": dataset.data_version,
        "model_version": convlstm.model_version,
        "checkpoint_path": str(convlstm.checkpoint_path),
        "checkpoint_sha256": convlstm.checkpoint_hash,
        "split": dataset.split,
        "events": list(dict.fromkeys(used_events)),
        "sample_count": sample_count,
        "temporal_step_minutes": 30,
        "thresholds_mm_h": thresholds,
        "masking": {
            "source": "target_mask intersected with finite observations and provider outputs",
            "requested_target_pixels": requested_target_pixels,
            "common_valid_pixels": common_valid_pixels,
            "excluded_pixels": requested_target_pixels - common_valid_pixels,
            "same_cells_for_all_providers": True,
        },
        "metric_pooling": (
            "error sums and TP/FP/FN/TN pooled over the identical valid held-out cells"
        ),
        "probabilistic_metrics": "NOT_APPLICABLE_DETERMINISTIC_FORECAST",
        "providers": providers,
    }
    return json_safe(report)


def evaluate_from_config(
    config_path: str | Path,
    *,
    checkpoint_path: str | Path | None = None,
    device: str = "auto",
) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = load_yaml(config_path)
    repo_root = config_path.parents[2]
    datasets, _ = build_datasets_from_config(config_path)
    checkpoint = Path(checkpoint_path) if checkpoint_path else (
        repo_root / config["artifacts"]["model_dir"] / config["model"]["version"] / "best.pt"
    )
    provider = ConvLSTMInference(checkpoint, device=device)
    report = evaluate_heldout(
        datasets["test"],
        provider,
        thresholds=[float(value) for value in config["evaluation"]["thresholds_mm_h"]],
    )
    output = repo_root / config["artifacts"]["evaluation_report"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report
