"""Fit probability calibration strictly on Validation split and evaluate probabilistic nowcasting metrics.

Ensures:
- ZERO held-out test data access during calibration or evaluation
- Brier Score, Brier Skill Score, ECE, ROC-AUC, PR-AUC, and reliability diagram bins
- Monotonic probability ordering enforcement
- Insufficient support handling for rare thresholds
- Saves:
  - models/probabilistic/isotonic_calibrator_v1.pkl
  - configs/probabilistic/probabilistic_nowcast_v1.yaml
  - reports/phase4c_probabilistic_evaluation.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
import zarr

from jalrakshak_ml.fusion.contracts import (
    GFSReplayProvider,
    PersistenceProvider,
    PystepsProvider,
)
from jalrakshak_ml.fusion.core import create_learned_gate_fusion
from jalrakshak_ml.fusion.gating import LearnedGatingModel
from jalrakshak_ml.fusion.probabilistic import (
    CalibratedProbabilisticNowcaster,
    compute_probabilistic_metrics,
)
from jalrakshak_ml.gfs_replay.core import utc


def run_probabilistic_pipeline(
    gpm_dataset_dir: str | Path = "data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
    gfs_replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_non_test_replay_v1",
    learned_gate_model_path: str | Path = "models/fusion/learned_gate_v1/model.pt",
    calibrator_output_path: str | Path = "models/probabilistic/isotonic_calibrator_v1.pkl",
    config_output_path: str | Path = "configs/probabilistic/probabilistic_nowcast_v1.yaml",
    report_output_path: str | Path = "reports/phase4c_probabilistic_evaluation.json",
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or [0.1, 1.0, 5.0, 10.0]
    gpm_root = Path(gpm_dataset_dir)
    gfs_root = Path(gfs_replay_root)

    manifest = json.loads((gpm_root / "manifest.json").read_text(encoding="utf-8"))
    val_event = next(e["event_id"] for e in manifest["events"] if e["split"] == "validation")
    zarr_path = gpm_root / "events" / f"{val_event}.zarr"
    root = zarr.open(str(zarr_path), mode="r")

    times_list = [str(t) for t in root["time"][:]]
    num_frames = len(times_list)
    history_len = 4
    lead_times = 4
    horizons = [30, 60, 90, 120]
    num_sequences = num_frames - history_len - lead_times + 1

    p_persistence = PersistenceProvider()
    p_pysteps = PystepsProvider()
    p_gfs = GFSReplayProvider(replay_root=gfs_root)
    gate_model = LearnedGatingModel(model_path=learned_gate_model_path)
    fusion_gate = create_learned_gate_fusion([p_persistence, p_pysteps, p_gfs], gate_model)

    prob_nowcaster = CalibratedProbabilisticNowcaster(
        thresholds=thresholds,
        horizons_min=horizons,
        min_support_count=50,
    )

    print(f"Collecting validation predictions across {num_sequences} sequences...")
    val_samples_for_fit: list[dict[str, Any]] = []
    val_eval_records: list[dict[str, Any]] = []

    for seq_idx in range(num_sequences):
        issue_idx = seq_idx + history_len - 1
        issue_time_dt = utc(times_list[issue_idx])

        history = root["rainfall"][seq_idx : seq_idx + history_len]
        target_frames = root["rainfall"][seq_idx + history_len : seq_idx + history_len + lead_times]
        valid_mask = root["valid_mask"][seq_idx + history_len : seq_idx + history_len + lead_times].astype(bool)

        # Predict with providers and fused gate
        res_persist = p_persistence.predict(history_frames=history, issue_time=issue_time_dt, lead_times=lead_times, event_id=val_event)
        res_pysteps = p_pysteps.predict(history_frames=history, issue_time=issue_time_dt, lead_times=lead_times, event_id=val_event)
        res_gfs = p_gfs.predict(history_frames=history, issue_time=issue_time_dt, lead_times=lead_times, event_id=val_event)

        provider_results = {
            "persistence": res_persist,
            "pysteps": res_pysteps,
            "gfs": res_gfs,
        }

        res_gate = fusion_gate.predict(history_frames=history, issue_time=issue_time_dt, lead_times=lead_times, event_id=val_event)

        # For each lead horizon, compute raw probabilities
        for lead_idx in range(lead_times):
            h_min = horizons[lead_idx]
            weights = res_gate.provenance.get("weights", {}).get(h_min, {"pysteps": 0.5, "gfs": 0.5})

            lead_preds = {p: res.rainfall_mm_h[lead_idx : lead_idx + 1] for p, res in provider_results.items()}
            raw_lead_probs = prob_nowcaster.compute_raw_probabilities(lead_preds, weights)

            val_samples_for_fit.append({
                "horizon_min": h_min,
                "raw_probs": {thr: arr[0] for thr, arr in raw_lead_probs.items()},
                "obs_frame": target_frames[lead_idx],
                "valid_mask": valid_mask[lead_idx],
            })

            val_eval_records.append({
                "seq_idx": seq_idx,
                "lead_idx": lead_idx,
                "horizon_min": h_min,
                "weights": weights,
                "raw_probs": {thr: arr[0] for thr, arr in raw_lead_probs.items()},
                "target_frame": target_frames[lead_idx],
                "valid_mask": valid_mask[lead_idx],
            })

    # Step 1: Fit Isotonic Regression strictly on VALIDATION split
    print("Fitting probability calibrators strictly on VALIDATION split...")
    fit_report = prob_nowcaster.fit_calibration_on_validation(val_samples_for_fit)

    # Save calibrator artifact
    cal_out = Path(calibrator_output_path)
    cal_out.parent.mkdir(parents=True, exist_ok=True)
    prob_nowcaster.save_calibration(cal_out)
    cal_sha256 = hashlib.sha256(cal_out.read_bytes()).hexdigest()

    # Step 2: Evaluate raw vs calibrated probabilistic metrics on Validation split
    print("Evaluating probabilistic metrics on Validation split...")
    evaluation_results: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "validation_event": val_event,
        "calibrator_artifact": str(cal_out.as_posix()),
        "calibrator_sha256": cal_sha256,
        "calibration_report": fit_report["calibrators"],
        "metrics_by_threshold_and_horizon": {},
    }

    for thr in thresholds:
        for h_min in horizons:
            key = f"h{h_min}_thr{thr}"
            h_records = [r for r in val_eval_records if r["horizon_min"] == h_min]

            all_y: list[np.ndarray] = []
            all_p_raw: list[np.ndarray] = []
            all_p_cal: list[np.ndarray] = []

            for r in h_records:
                obs = r["target_frame"]
                p_r = r["raw_probs"][thr]
                vmask = r["valid_mask"] & np.isfinite(obs) & np.isfinite(p_r)

                if np.any(vmask):
                    y_bin = (obs[vmask] > thr).astype(np.float32)
                    p_raw_sub = p_r[vmask]

                    cal_model = prob_nowcaster.calibrators.get((h_min, thr))
                    if cal_model is not None:
                        p_cal_sub = cal_model.predict(p_raw_sub)
                    else:
                        p_cal_sub = p_raw_sub

                    all_y.append(y_bin)
                    all_p_raw.append(p_raw_sub)
                    all_p_cal.append(p_cal_sub)

            if all_y:
                y_concat = np.concatenate(all_y)
                p_raw_concat = np.concatenate(all_p_raw)
                p_cal_concat = np.concatenate(all_p_cal)

                m_raw = compute_probabilistic_metrics(y_concat, p_raw_concat)
                m_cal = compute_probabilistic_metrics(y_concat, p_cal_concat)

                evaluation_results["metrics_by_threshold_and_horizon"][key] = {
                    "horizon_min": h_min,
                    "threshold_mm_h": thr,
                    "sample_count": len(y_concat),
                    "positive_count": int(np.sum(y_concat)),
                    "base_rate": float(np.mean(y_concat)),
                    "calibration_status": prob_nowcaster.calibration_status.get((h_min, thr), "UNCALIBRATED"),
                    "raw": m_raw,
                    "calibrated": m_cal,
                }

    # Step 3: Save YAML config
    cfg_out = Path(config_output_path)
    cfg_out.parent.mkdir(parents=True, exist_ok=True)
    cfg_yaml = {
        "model_version": "probabilistic_nowcast_v1",
        "calibrator_artifact": str(cal_out.as_posix()),
        "calibrator_sha256": cal_sha256,
        "calibration_method": "isotonic_regression",
        "calibration_split": "validation",
        "thresholds_mm_h": thresholds,
        "horizons_min": horizons,
        "min_support_count": 50,
        "calibrated_status": {
            f"{k[0]}_{k[1]}": v for k, v in prob_nowcaster.calibration_status.items()
        },
    }
    cfg_out.write_text(yaml.safe_dump(cfg_yaml, sort_keys=False), encoding="utf-8")

    # Step 4: Save JSON report
    rep_out = Path(report_output_path)
    rep_out.parent.mkdir(parents=True, exist_ok=True)
    rep_out.write_text(json.dumps(evaluation_results, indent=2), encoding="utf-8")

    print(f"Probabilistic artifacts saved to {cal_out}, {cfg_out}, and {rep_out}")
    return evaluation_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-output", default="reports/phase4c_probabilistic_evaluation.json")
    args = parser.parse_args()
    run_probabilistic_pipeline(report_output_path=args.report_output)
