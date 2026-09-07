"""Script to run Baseline Models (Persistence and PySTEPS) on real data."""

import logging
import json
from pathlib import Path
import pandas as pd
import numpy as np
import zarr

from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

ROOT = Path.cwd()
CUBES_DIR = ROOT / "data" / "processed" / "cubes"
REPORTS_DIR = ROOT / "reports"

def run_evaluation():
    weather_path = CUBES_DIR / "weather.zarr"
    if not weather_path.exists():
        log.error("weather.zarr not found")
        return

    root = zarr.open(str(weather_path), mode="r")
    gpm = root["rainfall_gpm"][:]
    times = root["time"][:]

    if len(gpm) < 10:
        log.error("Insufficient data for evaluation (need at least 10 frames)")
        return
        
    def evaluate_model_on_dataset(model, name, history_length=3, lead_times=4):
        preds_list = []
        obs_list = []
        
        for t in range(history_length, len(gpm) - lead_times):
            # The model predicts the NEXT lead_times frames
            history = gpm[t-history_length:t]
            future_obs = gpm[t:t+lead_times]
            
            try:
                # If model is persistence, it expects 2D
                if name == "persistence":
                    pred = model.predict(history[-1], lead_times)
                else:
                    pred = model.predict(history, lead_times)
                preds_list.append(pred)
                obs_list.append(future_obs)
            except Exception as e:
                log.error(f"{name} failed at index {t}: {e}")
                continue
                
        if not preds_list:
            return {}
            
        all_preds = np.stack(preds_list) # shape: (N, lead_times, H, W)
        all_obs = np.stack(obs_list) # shape: (N, lead_times, H, W)
        
        # We need to average metrics over N instances.
        # NowcastEvaluator expects (lead_times, H, W). We can compute metrics for each instance, then average.
        evaluator = NowcastEvaluator()
        
        # Let's collect results for each lead time
        metrics_by_lead_time = {lead: [] for lead in range(1, lead_times + 1)}
        
        for i in range(len(all_preds)):
            df = evaluator.evaluate_sequence(all_obs[i], all_preds[i])
            for _, row in df.iterrows():
                metrics_by_lead_time[row['lead_time']].append(row.to_dict())
                
        # Average / Pool
        final_results = []
        for lead in range(1, lead_times + 1):
            if not metrics_by_lead_time[lead]:
                continue
            df_lead = pd.DataFrame(metrics_by_lead_time[lead])
            
            # Start with averaged metrics (for mae, rmse, brier_score, reliability)
            avg_metrics = df_lead.mean().to_dict()
            
            # Recompute dichotomous metrics using pooled counts to avoid NaN skew and frame averaging issues
            for thresh in evaluator.thresholds:
                if f"hits_{thresh}" in df_lead.columns:
                    hits = df_lead[f"hits_{thresh}"].sum()
                    misses = df_lead[f"misses_{thresh}"].sum()
                    false_alarms = df_lead[f"false_alarms_{thresh}"].sum()
                    correct_negatives = df_lead[f"correct_negatives_{thresh}"].sum()
                    
                    pod = hits / (hits + misses) if (hits + misses) > 0 else np.nan
                    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) > 0 else np.nan
                    csi = hits / (hits + misses + false_alarms) if (hits + misses + false_alarms) > 0 else np.nan
                    bias = (hits + false_alarms) / (hits + misses) if (hits + misses) > 0 else np.nan
                    
                    precision = 1.0 - far if not np.isnan(far) else np.nan
                    f1 = 2 * (precision * pod) / (precision + pod) if not np.isnan(precision) and not np.isnan(pod) and (precision + pod) > 0 else np.nan
                    
                    avg_metrics[f"pod_{thresh}"] = pod
                    avg_metrics[f"far_{thresh}"] = far
                    avg_metrics[f"csi_{thresh}"] = csi
                    avg_metrics[f"f1_{thresh}"] = f1
                    avg_metrics[f"bias_{thresh}"] = bias
                    avg_metrics[f"hits_{thresh}"] = hits
                    avg_metrics[f"misses_{thresh}"] = misses
                    avg_metrics[f"false_alarms_{thresh}"] = false_alarms
                    avg_metrics[f"correct_negatives_{thresh}"] = correct_negatives

            avg_metrics['lead_time'] = lead
            final_results.append(avg_metrics)
            
        return final_results

    log.info(f"Loaded {len(gpm)} frames of GPM data")

    # Evaluate Persistence
    pers_model = PersistenceNowcast()
    pers_results = evaluate_model_on_dataset(pers_model, "persistence")
    
    # Evaluate PySTEPS
    # Since GPM is 30-min interval, optical flow might be tricky.
    pysteps_model = PystepsNowcast()
    pysteps_results = evaluate_model_on_dataset(pysteps_model, "pysteps")

    report = {
        "dataset_size": len(gpm),
        "start_time": str(times[0]),
        "end_time": str(times[-1]),
        "baselines": {
            "persistence": pers_results,
            "pysteps": pysteps_results
        }
    }

    out_path = REPORTS_DIR / "phase2_eval_metrics.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
        
    log.info(f"Saved evaluation metrics to {out_path}")

if __name__ == "__main__":
    run_evaluation()
