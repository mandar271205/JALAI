"""Phase 4C: Final locked held-out test evaluation.

Runs strictly ONCE on the 51 locked held-out test samples:
- mumbai_monsoon_2023_08_24
- mumbai_monsoon_2024_08_04
- mumbai_monsoon_2024_09_05

Evaluates:
1. Persistence
2. pySTEPS (operational nowcaster)
3. ConvLSTM V2 (experimental deep model; unvalidated)
4. GFS 0.25 NWP
5. Equal-weight Fusion
6. Horizon-fixed Fusion
7. Skill-derived Fusion
8. Supervised Learned Gate Fusion (trained strictly on Train split)
9. Calibrated Probabilistic Rainfall Forecasts (calibrated strictly on Validation split)

Applies strict operational model selection policy:
If learned gate does not beat pySTEPS on overall MAE AND overall RMSE,
retain OPERATIONAL_NOWCASTER=PySTEPS and OPERATIONAL_FUSION_PROVIDER=NONE.
"""
from __future__ import annotations

import argparse
import json
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
from jalrakshak_ml.fusion.probabilistic import (
    CalibratedProbabilisticNowcaster,
    compute_probabilistic_metrics,
)
from jalrakshak_ml.gfs_replay.core import utc


def evaluate_phase4c_heldout(
    *,
    benchmark_manifest_path: str | Path = "data/processed/benchmarks/mumbai_locked_test_51_v1.json",
    gpm_dataset_dir: str | Path = "data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
    gfs_replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_locked_test_replay_v1",
    calibrated_weights_path: str | Path = "configs/fusion/weights_v1.yaml",
    learned_gate_model_path: str | Path = "models/fusion/learned_gate_v1/model.pt",
    calibrator_artifact_path: str | Path = "models/probabilistic/isotonic_calibrator_v1.pkl",
    thresholds: list[float] | None = None,
    output_json_path: str | Path = "reports/phase4c_final_heldout_evaluation.json",
) -> dict[str, Any]:
    benchmark_path = Path(benchmark_manifest_path)
    gpm_root = Path(gpm_dataset_dir)
    gfs_root = Path(gfs_replay_root)
    weights_path = Path(calibrated_weights_path)
    gate_path = Path(learned_gate_model_path)
    cal_path = Path(calibrator_artifact_path)
    thresholds = thresholds or [0.1, 1.0, 5.0, 10.0]
    horizons = [30, 60, 90, 120]

    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    events_dir = gpm_root / "events"

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
    p_convlstm = ConvLSTMProvider()
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

    # Probabilistic nowcaster (loads validation-fitted calibrators)
    prob_nowcaster = CalibratedProbabilisticNowcaster(
        thresholds=thresholds,
        horizons_min=horizons,
        min_support_count=50,
    )
    prob_nowcaster.load_calibration(cal_path)

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
    prob_records_by_lead: dict[int, list[dict[str, Any]]] = {h: [] for h in horizons}
    sample_weights_log: list[dict[str, Any]] = []

    total_requested_cells = 0
    total_valid_cells = 0

    print("Evaluating models on locked 51 held-out test samples...")
    for event_cfg in benchmark["events"]:
        event_id = event_cfg["event_id"]
        zarr_path = events_dir / f"{event_id}.zarr"
        root = zarr.open(str(zarr_path), mode="r")
        times_list = [str(t) for t in root["time"][:]]
        time_to_idx = {t: idx for idx, t in enumerate(times_list)}

        for sample in event_cfg["samples"]:
            issue_time_dt = utc(sample["issue_time"])

            # Inputs
            input_indices = [time_to_idx[t] for t in sample["input_times"]]
            history_frames = root["rainfall"][input_indices]

            # Targets
            target_indices = [time_to_idx[t] for t in sample["target_times"]]
            obs_frames = root["rainfall"][target_indices]
            obs_valid_mask = root["valid_mask"][target_indices].astype(bool)

            preds: dict[str, np.ndarray] = {}

            # Standalone providers
            res_persist = p_persistence.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["persistence"] = res_persist.rainfall_mm_h

            res_pysteps = p_pysteps.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["pysteps"] = res_pysteps.rainfall_mm_h

            res_gfs = p_gfs.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["gfs"] = res_gfs.rainfall_mm_h

            # Fusions
            res_equal = fusion_equal.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["fusion_equal"] = res_equal.rainfall_mm_h

            res_hfixed = fusion_horizon_fixed.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["fusion_horizon_fixed"] = res_hfixed.rainfall_mm_h

            res_skill = fusion_skill.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["fusion_skill_derived"] = res_skill.rainfall_mm_h

            res_gate = fusion_learned_gate.predict(history_frames=history_frames, issue_time=issue_time_dt, lead_times=4, event_id=event_id)
            preds["learned_gate"] = res_gate.rainfall_mm_h

            weights_log = res_gate.provenance.get("weights", {})
            sample_weights_log.append({
                "event_id": event_id,
                "issue_time": sample["issue_time"],
                "weights": weights_log,
            })

            # Common mask across all predictions and observations
            common_mask = obs_valid_mask & np.isfinite(obs_frames)
            for p_arr in preds.values():
                common_mask &= np.isfinite(p_arr)

            total_requested_cells += int(obs_valid_mask.sum())
            total_valid_cells += int(common_mask.sum())

            # Evaluate deterministic models on common mask
            for m_name in models_to_evaluate:
                df = evaluator.evaluate_sequence(
                    obs_frames,
                    preds[m_name],
                    valid_mask=common_mask,
                )
                metric_rows[m_name].append(df.to_dict(orient="records"))

            # Evaluate probabilistic predictions
            provider_results = {
                "persistence": res_persist,
                "pysteps": res_pysteps,
                "gfs": res_gfs,
            }
            for lead_idx in range(4):
                h_min = horizons[lead_idx]
                w_lead = weights_log.get(h_min, {"pysteps": 0.5, "gfs": 0.5})

                # Compute raw and calibrated probabilities
                sub_prov = {p: res.rainfall_mm_h[lead_idx : lead_idx + 1] for p, res in provider_results.items()}
                raw_lead = prob_nowcaster.compute_raw_probabilities(sub_prov, w_lead)

                obs_lead = obs_frames[lead_idx]
                c_mask_lead = common_mask[lead_idx]

                cal_lead = {}
                for thr in thresholds:
                    p_raw = raw_lead[thr][0]
                    cal_m = prob_nowcaster.calibrators.get((h_min, thr))
                    if cal_m is not None:
                        orig_sh = p_raw.shape
                        p_cal = cal_m.predict(p_raw.flatten()).reshape(orig_sh).astype(np.float32)
                    else:
                        p_cal = p_raw
                    cal_lead[thr] = np.clip(p_cal, 0.0, 1.0)

                # Ensure calibrated threshold monotonicity
                for i in range(1, len(thresholds)):
                    p_prev = thresholds[i - 1]
                    p_curr = thresholds[i]
                    cal_lead[p_curr] = np.minimum(cal_lead[p_curr], cal_lead[p_prev])

                prob_records_by_lead[h_min].append({
                    "raw_probs": {thr: raw_lead[thr][0] for thr in thresholds},
                    "cal_probs": cal_lead,
                    "target_frame": obs_lead,
                    "valid_mask": c_mask_lead,
                })

    # Pool deterministic metrics
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

    # Evaluate probabilistic metrics on held-out test
    prob_evaluation: dict[str, Any] = {}
    for thr in thresholds:
        prob_evaluation[f"thr_{thr}"] = {}
        for h_min in horizons:
            records = prob_records_by_lead[h_min]
            all_y = []
            all_p_raw = []
            all_p_cal = []

            for r in records:
                obs = r["target_frame"]
                p_c = r["cal_probs"][thr]
                p_r = r["raw_probs"][thr]
                vmask = r["valid_mask"] & np.isfinite(obs) & np.isfinite(p_c)

                if np.any(vmask):
                    all_y.append((obs[vmask] > thr).astype(np.float32))
                    all_p_raw.append(p_r[vmask])
                    all_p_cal.append(p_c[vmask])

            if all_y:
                y_concat = np.concatenate(all_y)
                p_raw_concat = np.concatenate(all_p_raw)
                p_cal_concat = np.concatenate(all_p_cal)

                m_raw = compute_probabilistic_metrics(y_concat, p_raw_concat)
                m_cal = compute_probabilistic_metrics(y_concat, p_cal_concat)

                prob_evaluation[f"thr_{thr}"][f"h_{h_min}"] = {
                    "horizon_min": h_min,
                    "threshold_mm_h": thr,
                    "sample_count": len(y_concat),
                    "positive_count": int(np.sum(y_concat)),
                    "base_rate": float(np.mean(y_concat)),
                    "calibration_status": prob_nowcaster.calibration_status.get((h_min, thr), "UNCALIBRATED"),
                    "raw": m_raw,
                    "calibrated": m_cal,
                }

    # Primary selection criteria: overall MAE and RMSE
    pysteps_mae = pooled_by_model["pysteps"]["overall"]["mae"]
    pysteps_rmse = pooled_by_model["pysteps"]["overall"]["rmse"]

    winning_fusion = None
    best_fusion_mae = float("inf")
    best_fusion_rmse = float("inf")

    candidates = ["fusion_equal", "fusion_horizon_fixed", "fusion_skill_derived", "learned_gate"]
    for cand in candidates:
        c_mae = pooled_by_model[cand]["overall"]["mae"]
        c_rmse = pooled_by_model[cand]["overall"]["rmse"]
        if c_mae < pysteps_mae and c_rmse < pysteps_rmse:
            if c_mae < best_fusion_mae:
                winning_fusion = cand
                best_fusion_mae = c_mae
                best_fusion_rmse = c_rmse

    operational_fusion = winning_fusion if winning_fusion else "NONE"
    operational_nowcaster = winning_fusion if winning_fusion else "PySTEPS"

    summary = {
        "evaluation_name": "phase4c_final_heldout_evaluation",
        "created_at": datetime.now(UTC).isoformat(),
        "total_test_events": len(benchmark["events"]),
        "total_test_samples": benchmark["total_samples"],
        "common_valid_cells": total_valid_cells,
        "coverage_fraction": float(total_valid_cells / max(1, total_requested_cells)),
        "primary_selection": {
            "operational_nowcaster": operational_nowcaster,
            "operational_fusion_provider": operational_fusion,
            "pysteps_mae": pysteps_mae,
            "pysteps_rmse": pysteps_rmse,
            "winning_fusion": winning_fusion,
            "best_fusion_mae": best_fusion_mae if winning_fusion else None,
            "best_fusion_rmse": best_fusion_rmse if winning_fusion else None,
            "selection_rule": "Fusion must beat PySTEPS on BOTH overall MAE and overall RMSE.",
        },
        "models": pooled_by_model,
        "probabilistic_evaluation": prob_evaluation,
        "sample_weights_log": sample_weights_log[:4],
    }

    out_path = Path(output_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Final held-out evaluation successfully saved to {out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", default="reports/phase4c_final_heldout_evaluation.json")
    args = parser.parse_args()
    evaluate_phase4c_heldout(output_json_path=args.output_json)
