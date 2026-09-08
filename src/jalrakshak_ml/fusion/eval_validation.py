"""Phase 4C: Validation split evaluation comparing all providers and fusion baselines.

Evaluates on the Validation event (mumbai_monsoon_2023_07_25):
- Persistence
- PySTEPS
- ConvLSTM V2 (experimental, unvalidated)
- GFS 0.25 NWP
- Equal fusion (PySTEPS + GFS)
- Horizon-fixed fusion
- Skill-derived fusion (calibrated weights)
- Supervised Learned Gate (trained strictly on Train split mumbai_monsoon_2023_07_18)

Held-out TEST events remain STRICTLY UNTOUCHED.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
import zarr

from jalrakshak_ml.deep_nowcast.verification import pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.fusion.contracts import (
    ConvLSTMProvider,
    GFSReplayProvider,
    PersistenceProvider,
    PystepsProvider,
)
from jalrakshak_ml.fusion.core import (
    MultiModelFusion,
    create_equal_weight_fusion,
    create_horizon_fixed_fusion,
    create_learned_gate_fusion,
    create_skill_derived_fusion,
)
from jalrakshak_ml.fusion.gating import LearnedGatingModel
from jalrakshak_ml.gfs_replay.core import utc


def evaluate_phase4c_validation(
    *,
    gpm_dataset_dir: str | Path = "data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
    gfs_replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_non_test_replay_v1",
    learned_gate_model_path: str | Path = "models/fusion/learned_gate_v1/model.pt",
    calibrated_weights_path: str | Path = "configs/fusion/weights_v1.yaml",
    thresholds: list[float] | None = None,
    output_json_path: str | Path = "reports/phase4c_validation_evaluation.json",
) -> dict[str, Any]:
    gpm_root = Path(gpm_dataset_dir)
    gfs_root = Path(gfs_replay_root)
    weights_path = Path(calibrated_weights_path)
    gate_path = Path(learned_gate_model_path)
    thresholds = thresholds or [0.1, 1.0, 5.0, 10.0]

    manifest = json.loads((gpm_root / "manifest.json").read_text(encoding="utf-8"))
    val_event = next(e["event_id"] for e in manifest["events"] if e["split"] == "validation")
    zarr_path = gpm_root / "events" / f"{val_event}.zarr"
    root = zarr.open(str(zarr_path), mode="r")

    times_list = [str(t) for t in root["time"][:]]
    num_frames = len(times_list)

    # In 24-frame event with history=4 and lead=4: 17 valid sequences
    history_len = 4
    lead_times = 4
    num_sequences = num_frames - history_len - lead_times + 1

    # Load calibrated skill weights
    if weights_path.exists():
        weights_manifest = yaml.safe_load(weights_path.read_text(encoding="utf-8"))
        calibrated_weights = {
            int(h): weights_manifest["weights_by_horizon"][h]
            for h in weights_manifest["weights_by_horizon"]
        }
    else:
        calibrated_weights = {
            30: {"pysteps": 0.70, "gfs": 0.30, "persistence": 0.0, "convlstm_v2": 0.0},
            60: {"pysteps": 0.55, "gfs": 0.45, "persistence": 0.0, "convlstm_v2": 0.0},
            90: {"pysteps": 0.40, "gfs": 0.60, "persistence": 0.0, "convlstm_v2": 0.0},
            120: {"pysteps": 0.25, "gfs": 0.75, "persistence": 0.0, "convlstm_v2": 0.0},
        }

    # Initialize providers
    p_persistence = PersistenceProvider()
    p_pysteps = PystepsProvider()
    p_convlstm = ConvLSTMProvider()  # Checkpoint not present -> unavailable
    p_gfs = GFSReplayProvider(replay_root=gfs_root)

    eval_providers = [p_persistence, p_pysteps, p_gfs]
    if p_convlstm.is_available:
        eval_providers.append(p_convlstm)

    # Initialize fusions
    fusion_equal = create_equal_weight_fusion([p_pysteps, p_gfs])
    fusion_horizon_fixed = create_horizon_fixed_fusion([p_pysteps, p_gfs])
    fusion_skill = create_skill_derived_fusion([p_pysteps, p_gfs], calibrated_weights)

    gate_model = LearnedGatingModel(model_path=gate_path)
    fusion_learned_gate = create_learned_gate_fusion([p_persistence, p_pysteps, p_gfs], gate_model)

    evaluator = NowcastEvaluator(thresholds=thresholds)

    models_to_evaluate = [
        "persistence",
        "pysteps",
        "gfs",
        "fusion_equal",
        "fusion_horizon_fixed",
        "fusion_skill_derived",
        "learned_gate",
    ]
    if p_convlstm.is_available:
        models_to_evaluate.append("convlstm_v2")

    metric_rows: dict[str, list[list[dict[str, Any]]]] = {m: [] for m in models_to_evaluate}
    applied_gate_weights: list[dict[str, Any]] = []

    total_requested_cells = 0
    total_valid_cells = 0

    print(f"Evaluating {len(models_to_evaluate)} models over {num_sequences} validation sequences...")
    for seq_idx in range(num_sequences):
        issue_idx = seq_idx + history_len - 1
        issue_time_str = times_list[issue_idx]
        issue_time_dt = utc(issue_time_str)

        history_frames = root["rainfall"][seq_idx : seq_idx + history_len]  # [4, 256, 256]
        target_frames = root["rainfall"][seq_idx + history_len : seq_idx + history_len + lead_times]  # [4, 256, 256]
        target_valid_mask = root["valid_mask"][seq_idx + history_len : seq_idx + history_len + lead_times].astype(bool)

        preds: dict[str, np.ndarray] = {}

        # 1. Persistence
        res_persist = p_persistence.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["persistence"] = res_persist.rainfall_mm_h

        # 2. PySTEPS
        res_pysteps = p_pysteps.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["pysteps"] = res_pysteps.rainfall_mm_h

        # 3. GFS
        res_gfs = p_gfs.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["gfs"] = res_gfs.rainfall_mm_h

        # 4. Equal fusion
        res_equal = fusion_equal.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["fusion_equal"] = res_equal.rainfall_mm_h

        # 5. Horizon-fixed fusion
        res_hfixed = fusion_horizon_fixed.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["fusion_horizon_fixed"] = res_hfixed.rainfall_mm_h

        # 6. Skill-derived fusion
        res_skill = fusion_skill.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["fusion_skill_derived"] = res_skill.rainfall_mm_h

        # 7. Learned gate fusion
        res_gate = fusion_learned_gate.predict(
            history_frames=history_frames,
            issue_time=issue_time_dt,
            lead_times=lead_times,
            event_id=val_event,
        )
        preds["learned_gate"] = res_gate.rainfall_mm_h

        applied_gate_weights.append({
            "issue_time": issue_time_str,
            "weights": res_gate.provenance.get("weights", {}),
        })

        # Intersection valid mask across all predictions and observations
        common_mask = target_valid_mask & np.isfinite(target_frames)
        for p_arr in preds.values():
            common_mask &= np.isfinite(p_arr)

        total_requested_cells += int(target_valid_mask.sum())
        total_valid_cells += int(common_mask.sum())

        for m_name in models_to_evaluate:
            df = evaluator.evaluate_sequence(
                target_frames,
                preds[m_name],
                valid_mask=common_mask,
            )
            metric_rows[m_name].append(df.to_dict(orient="records"))

    # Pool metrics for each model
    pooled_by_model: dict[str, Any] = {}
    for m_name in models_to_evaluate:
        pooled = pool_metric_rows(metric_rows[m_name], thresholds, temporal_step_minutes=30)
        for item in [pooled["overall"]] + pooled["by_lead"]:
            for thr in thresholds:
                hits = item.get(f"hits_{thr}", 0)
                misses = item.get(f"misses_{thr}", 0)
                if hits + misses == 0:
                    item[f"pod_{thr}"] = "insufficient_support"
                    item[f"csi_{thr}"] = "insufficient_support"
                    item[f"f1_{thr}"] = "insufficient_support"
                    item[f"bias_{thr}"] = "insufficient_support"
        pooled_by_model[m_name] = pooled

    # Verification of primary criteria
    pysteps_mae = pooled_by_model["pysteps"]["overall"]["mae"]
    pysteps_rmse = pooled_by_model["pysteps"]["overall"]["rmse"]
    gate_mae = pooled_by_model["learned_gate"]["overall"]["mae"]
    gate_rmse = pooled_by_model["learned_gate"]["overall"]["rmse"]

    summary = {
        "evaluation_name": "phase4c_validation_evaluation",
        "split": "validation",
        "validation_event": val_event,
        "created_at": datetime.now(UTC).isoformat(),
        "total_sequences": num_sequences,
        "total_samples": num_sequences * lead_times,
        "common_valid_cells": total_valid_cells,
        "coverage_fraction": float(total_valid_cells / max(1, total_requested_cells)),
        "models": pooled_by_model,
        "learned_gate_vs_pysteps": {
            "pysteps_mae": pysteps_mae,
            "pysteps_rmse": pysteps_rmse,
            "gate_mae": gate_mae,
            "gate_rmse": gate_rmse,
            "mae_delta": gate_mae - pysteps_mae,
            "rmse_delta": gate_rmse - pysteps_rmse,
            "gate_beats_pysteps_overall": bool(gate_mae < pysteps_mae and gate_rmse < pysteps_rmse),
        },
        "sample_gate_weights": applied_gate_weights[:3],
    }

    out_path = Path(output_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Validation evaluation written to {out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", default="reports/phase4c_validation_evaluation.json")
    args = parser.parse_args()
    evaluate_phase4c_validation(output_json_path=args.output_json)
