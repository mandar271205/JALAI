import json
import sys

def summarize_prob(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)["probabilistic_evaluation"]
    print("=" * 95)
    print(f"{'Threshold':<12} | {'Lead':<6} | {'Samples':<10} | {'Positives':<10} | {'BS (Raw)':<10} | {'BS (Cal)':<10} | {'BSS (Cal)':<10} | {'ROC-AUC':<10}")
    print("=" * 95)
    for thr_key, h_map in d.items():
        for h_key, item in h_map.items():
            thr = item["threshold_mm_h"]
            h = item["horizon_min"]
            n = item["sample_count"]
            pos = item["positive_count"]
            bs_raw = item["raw"].get("brier_score", "N/A")
            bs_cal = item["calibrated"].get("brier_score", "N/A")
            bss_cal = item["calibrated"].get("brier_skill_score", "N/A")
            auc = item["calibrated"].get("roc_auc", "N/A")
            print(f"> {thr:<8} mm/h | +{h:<4}m | {n:<10} | {pos:<10} | {bs_raw:<10} | {bs_cal:<10} | {bss_cal:<10} | {auc:<10}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "reports/phase4c_final_heldout_evaluation.json"
    summarize_prob(path)
