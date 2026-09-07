"""Held-out evaluation shared by Persistence, pySTEPS, and ConvLSTM."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.dataset import build_datasets_from_config
from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


def _pooled_metrics(sample_rows: list[list[dict[str, Any]]], thresholds: list[float]) -> list[dict[str, Any]]:
    """Match Phase-2 semantics: average continuous values; pool event counts."""
    if not sample_rows:
        return []
    by_lead: dict[int, list[dict[str, Any]]] = {}
    for rows in sample_rows:
        for row in rows:
            by_lead.setdefault(int(row["lead_time"]), []).append(row)
    output = []
    for lead in sorted(by_lead):
        frame = pd.DataFrame(by_lead[lead])
        row: dict[str, Any] = {
            "lead_time": lead,
            "horizon_minutes": lead * 30,
            "mae": float(frame["mae"].mean()),
            "rmse": float(frame["rmse"].mean()),
        }
        for threshold in thresholds:
            suffix = str(threshold)
            hits = float(frame[f"hits_{suffix}"].sum())
            misses = float(frame[f"misses_{suffix}"].sum())
            false_alarms = float(frame[f"false_alarms_{suffix}"].sum())
            correct_negatives = float(frame[f"correct_negatives_{suffix}"].sum())
            pod = hits / (hits + misses) if hits + misses else math.nan
            far = false_alarms / (hits + false_alarms) if hits + false_alarms else math.nan
            csi = hits / (hits + misses + false_alarms) if hits + misses + false_alarms else math.nan
            bias = (hits + false_alarms) / (hits + misses) if hits + misses else math.nan
            precision = 1.0 - far if math.isfinite(far) else math.nan
            f1 = (
                2.0 * precision * pod / (precision + pod)
                if math.isfinite(precision) and math.isfinite(pod) and precision + pod
                else math.nan
            )
            row.update({
                f"pod_{suffix}": pod,
                f"far_{suffix}": far,
                f"csi_{suffix}": csi,
                f"f1_{suffix}": f1,
                f"bias_{suffix}": bias,
                f"hits_{suffix}": hits,
                f"misses_{suffix}": misses,
                f"false_alarms_{suffix}": false_alarms,
                f"correct_negatives_{suffix}": correct_negatives,
            })
        output.append(row)
    return output


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def evaluate_heldout(
    dataset,
    convlstm: ConvLSTMInference,
    *,
    thresholds: list[float] | None = None,
    max_samples: int | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or [0.1, 1.0, 5.0]
    evaluator = NowcastEvaluator(thresholds=thresholds)
    persistence = PersistenceNowcast()
    pysteps = PystepsNowcast()
    rows = {"persistence": [], "pysteps": [], "convlstm": []}
    used_events: list[str] = []
    sample_count = min(len(dataset), max_samples) if max_samples else len(dataset)
    for index in range(sample_count):
        raw = dataset.get_raw(index)
        history = raw["inputs"]
        rainfall_history = history[:, dataset.input_channels.index("rainfall")]
        observation = raw["target"][:, 0]
        lead_times = observation.shape[0]
        predictions = {
            "persistence": persistence.predict(rainfall_history[-1], lead_times),
            "pysteps": pysteps.predict(rainfall_history, lead_times),
            "convlstm": convlstm.predict(history, lead_times),
        }
        for name, prediction in predictions.items():
            frame = evaluator.evaluate_sequence(observation, prediction)
            rows[name].append(frame.to_dict(orient="records"))
        used_events.append(raw["metadata"]["event_id"])
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
        "metric_pooling": "TP/FP/FN/TN pooled over all valid held-out space-time cells",
        "probabilistic_metrics": "NOT_APPLICABLE_DETERMINISTIC_FORECAST",
        "providers": {
            "persistence": {"metrics": _pooled_metrics(rows["persistence"], thresholds)},
            "pysteps": {
                "available": bool(pysteps._is_available),
                "fallback_to_persistence": bool(not pysteps._is_available and pysteps.fallback),
                "metrics": _pooled_metrics(rows["pysteps"], thresholds),
            },
            "convlstm": {"metrics": _pooled_metrics(rows["convlstm"], thresholds)},
        },
    }
    return _json_safe(report)


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
