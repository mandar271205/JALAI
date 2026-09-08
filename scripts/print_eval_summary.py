import json
import sys

def summarize(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    print(f"=== {d.get('evaluation_name', 'Evaluation Summary')} ===")
    print(f"Split: {d.get('split', 'N/A')} | Samples: {d.get('total_samples', 'N/A')} | Valid Cells: {d.get('common_valid_cells', 'N/A'):,}")
    print("-" * 65)
    print(f"{'Model':<24} | {'MAE (mm/h)':<10} | {'RMSE (mm/h)':<10} | {'Bias':<10}")
    print("-" * 65)
    for m, v in d["models"].items():
        mae = v["overall"]["mae"]
        rmse = v["overall"]["rmse"]
        bias = v["overall"]["bias"]
        print(f"{m:<24} | {mae:<10.4f} | {rmse:<10.4f} | {bias:<10.4f}")
    print("-" * 65)
    print("Performance by Horizon (MAE):")
    horizons = [30, 60, 90, 120]
    header = f"{'Model':<24} | " + " | ".join(f"+{h}m" for h in horizons)
    print(header)
    print("-" * len(header))
    for m, v in d["models"].items():
        maes = [lead["mae"] for lead in v["by_lead"]]
        mae_str = " | ".join(f"{val:<4.4f}" for val in maes)
        print(f"{m:<24} | {mae_str}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "reports/phase4c_validation_evaluation.json"
    summarize(path)
