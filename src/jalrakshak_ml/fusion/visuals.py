"""Robust scientific figure generator for Phase 4C using PIL.

Generates reproducible figures directly from evaluation JSON artifacts:
1. reports/figures/phase4c_lead_time_skill.png (MAE & RMSE progression)
2. reports/figures/phase4c_provider_fusion_weights.png (Dynamic provider weights)
3. reports/figures/phase4c_reliability_diagrams.png (Reliability curves)
4. reports/figures/phase4c_spatial_forecast_and_uncertainty.png (Multi-provider maps & probabilities)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def plot_lead_time_skill(
    heldout_json_path: str | Path = "reports/phase4c_final_heldout_evaluation.json",
    output_png: str | Path = "reports/figures/phase4c_lead_time_skill.png",
) -> None:
    path = Path(heldout_json_path)
    if not path.exists():
        print(f"Heldout evaluation not found at {path}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    models = data["models"]
    horizons = [30, 60, 90, 120]

    width, height = 1100, 520
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    f_title = _get_font(18)
    f_axis = _get_font(13)
    f_legend = _get_font(11)

    # Title
    draw.text((width // 2 - 220, 20), "Phase 4C: Forecast Error Progression vs Horizon", fill=(20, 20, 20), font=f_title)

    # Model styles
    styles = {
        "persistence": {"color": (130, 130, 130), "label": "Persistence"},
        "pysteps": {"color": (31, 119, 180), "label": "PySTEPS (Operational)", "thick": 3},
        "gfs": {"color": (255, 127, 14), "label": "GFS 0.25 NWP"},
        "fusion_equal": {"color": (44, 160, 44), "label": "Equal Fusion"},
        "fusion_horizon_fixed": {"color": (148, 103, 189), "label": "Horizon-Fixed Fusion"},
        "fusion_skill_derived": {"color": (140, 86, 75), "label": "Skill-Derived Fusion"},
        "learned_gate": {"color": (214, 39, 40), "label": "Learned Gate (MLP)", "thick": 3},
    }

    def draw_chart(ax_rect, metric_key, y_max, title_text, y_label):
        x0, y0, x1, y1 = ax_rect
        # Background & border
        draw.rectangle([x0, y0, x1, y1], fill=(250, 250, 250), outline=(200, 200, 200), width=1)

        # Gridlines
        for i in range(5):
            val = i * (y_max / 4)
            gy = int(y1 - (val / y_max) * (y1 - y0))
            draw.line([(x0, gy), (x1, gy)], fill=(230, 230, 230), width=1)
            draw.text((x0 - 45, gy - 7), f"{val:.2f}", fill=(80, 80, 80), font=f_axis)

        # X-ticks
        x_coords = []
        for i, h in enumerate(horizons):
            gx = int(x0 + (i / 3) * (x1 - x0))
            x_coords.append(gx)
            draw.line([(gx, y0), (gx, y1)], fill=(230, 230, 230), width=1)
            draw.text((gx - 14, y1 + 8), f"+{h}m", fill=(60, 60, 60), font=f_axis)

        # Chart titles
        draw.text((x0 + (x1 - x0) // 2 - 50, y0 - 30), title_text, fill=(30, 30, 30), font=f_axis)
        draw.text((x0 - 45, y0 - 30), y_label, fill=(60, 60, 60), font=f_axis)

        # Plot lines
        for m_name, st in styles.items():
            if m_name not in models:
                continue
            vals = [lead[metric_key] for lead in models[m_name]["by_lead"]]
            pts = []
            for gx, val in zip(x_coords, vals):
                gy = int(y1 - (val / y_max) * (y1 - y0))
                pts.append((gx, gy))

            col = st["color"]
            thk = st.get("thick", 2)
            for j in range(len(pts) - 1):
                draw.line([pts[j], pts[j + 1]], fill=col, width=thk)
            for gx, gy in pts:
                draw.ellipse([gx - 3, gy - 3, gx + 3, gy + 3], fill=col)

    # Left chart: MAE
    draw_chart((90, 90, 480, 430), "mae", 1.4, "MAE Progression", "mm/h")
    # Right chart: RMSE
    draw_chart((590, 90, 980, 430), "rmse", 2.0, "RMSE Progression", "mm/h")

    # Legend at bottom
    lx = 100
    ly = 480
    for m_name, st in styles.items():
        col = st["color"]
        lbl = st["label"]
        draw.rectangle([lx, ly, lx + 14, ly + 10], fill=col)
        draw.text((lx + 20, ly - 2), lbl, fill=(40, 40, 40), font=f_legend)
        lx += len(lbl) * 7 + 35

    out_p = Path(output_png)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_p)
    print(f"Saved lead time skill figure to {out_p}")


def plot_provider_fusion_weights(
    heldout_json_path: str | Path = "reports/phase4c_final_heldout_evaluation.json",
    output_png: str | Path = "reports/figures/phase4c_provider_fusion_weights.png",
) -> None:
    path = Path(heldout_json_path)
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    weights_logs = data.get("sample_weights_log", [])
    if not weights_logs:
        return

    horizons = [30, 60, 90, 120]
    p_weights: dict[str, list[float]] = {"pysteps": [], "gfs": [], "persistence": []}

    for h in horizons:
        h_str = str(h)
        for p in p_weights:
            vals = [log["weights"].get(h_str, {}).get(p, 0.0) for log in weights_logs if h_str in log["weights"]]
            p_weights[p].append(float(np.mean(vals)) if vals else 0.0)

    width, height = 750, 460
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    f_title = _get_font(17)
    f_axis = _get_font(13)
    f_legend = _get_font(11)

    draw.text((160, 20), "Learned Gate Dynamic Provider Weight Allocation", fill=(20, 20, 20), font=f_title)

    x0, y0, x1, y1 = 90, 70, 680, 380
    draw.rectangle([x0, y0, x1, y1], fill=(250, 250, 250), outline=(200, 200, 200), width=1)

    # Grid & Y labels
    for i in range(5):
        val = i * 0.25
        gy = int(y1 - val * (y1 - y0))
        draw.line([(x0, gy), (x1, gy)], fill=(230, 230, 230), width=1)
        draw.text((x0 - 42, gy - 7), f"{val:.2f}", fill=(80, 80, 80), font=f_axis)

    colors = {
        "pysteps": (31, 119, 180),
        "gfs": (255, 127, 14),
        "persistence": (140, 140, 140),
    }

    group_w = (x1 - x0) // 4
    bar_w = 26

    for i, h in enumerate(horizons):
        gx = x0 + i * group_w + 30
        draw.text((gx + 22, y1 + 10), f"+{h}m", fill=(40, 40, 40), font=f_axis)

        # PySTEPS bar
        w_py = p_weights["pysteps"][i]
        bh_py = int(w_py * (y1 - y0))
        draw.rectangle([gx, y1 - bh_py, gx + bar_w, y1], fill=colors["pysteps"])

        # GFS bar
        w_gfs = p_weights["gfs"][i]
        bh_gfs = int(w_gfs * (y1 - y0))
        draw.rectangle([gx + bar_w + 4, y1 - bh_gfs, gx + 2 * bar_w + 4, y1], fill=colors["gfs"])

        # Persistence bar
        w_per = p_weights["persistence"][i]
        bh_per = int(w_per * (y1 - y0))
        draw.rectangle([gx + 2 * bar_w + 8, y1 - bh_per, gx + 3 * bar_w + 8, y1], fill=colors["persistence"])

    # Legend
    lx = 220
    ly = 420
    for p, col in colors.items():
        draw.rectangle([lx, ly, lx + 16, ly + 10], fill=col)
        draw.text((lx + 22, ly - 2), p.upper(), fill=(40, 40, 40), font=f_legend)
        lx += 120

    out_p = Path(output_png)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_p)
    print(f"Saved provider fusion weights figure to {out_p}")


def plot_reliability_diagrams(
    prob_json_path: str | Path = "reports/phase4c_probabilistic_evaluation.json",
    output_png: str | Path = "reports/figures/phase4c_reliability_diagrams.png",
) -> None:
    path = Path(prob_json_path)
    if not path.exists():
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    metrics = data.get("metrics_by_threshold_and_horizon", {})

    width, height = 960, 680
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    f_title = _get_font(18)
    f_axis = _get_font(12)
    f_sub = _get_font(13)
    f_legend = _get_font(11)

    draw.text((240, 20), "Phase 4C: Exceedance Probability Reliability Diagrams", fill=(20, 20, 20), font=f_title)

    panels = [
        ("h30_thr0.1", "+30m | Thr > 0.1 mm/h", (80, 80, 460, 330)),
        ("h60_thr0.1", "+60m | Thr > 0.1 mm/h", (540, 80, 920, 330)),
        ("h30_thr1.0", "+30m | Thr > 1.0 mm/h", (80, 390, 460, 640)),
        ("h60_thr1.0", "+60m | Thr > 1.0 mm/h", (540, 390, 920, 640)),
    ]

    for key, title, (x0, y0, x1, y1) in panels:
        draw.rectangle([x0, y0, x1, y1], fill=(252, 252, 252), outline=(210, 210, 210), width=1)
        draw.text((x0 + 10, y0 + 10), title, fill=(20, 20, 20), font=f_sub)

        # Perfect calibration line (diagonal)
        draw.line([(x0, y1), (x1, y0)], fill=(160, 160, 160), width=1)

        # Grid lines
        for step in [0.25, 0.5, 0.75]:
            gx = int(x0 + step * (x1 - x0))
            gy = int(y1 - step * (y1 - y0))
            draw.line([(gx, y0), (gx, y1)], fill=(240, 240, 240), width=1)
            draw.line([(x0, gy), (x1, gy)], fill=(240, 240, 240), width=1)

        entry = metrics.get(key)
        if entry:
            # Raw bins
            raw_bins = entry.get("raw", {}).get("reliability_bins", [])
            raw_pts = []
            for b in raw_bins:
                if b["count"] > 0:
                    px = int(x0 + b["predicted_prob_mean"] * (x1 - x0))
                    py = int(y1 - b["observed_frequency"] * (y1 - y0))
                    raw_pts.append((px, py))
            for i in range(len(raw_pts) - 1):
                draw.line([raw_pts[i], raw_pts[i + 1]], fill=(255, 127, 14), width=2)
            for px, py in raw_pts:
                draw.rectangle([px - 2, py - 2, px + 2, py + 2], fill=(255, 127, 14))

            # Calibrated bins
            cal_bins = entry.get("calibrated", {}).get("reliability_bins", [])
            cal_pts = []
            for b in cal_bins:
                if b["count"] > 0:
                    px = int(x0 + b["predicted_prob_mean"] * (x1 - x0))
                    py = int(y1 - b["observed_frequency"] * (y1 - y0))
                    cal_pts.append((px, py))
            for i in range(len(cal_pts) - 1):
                draw.line([cal_pts[i], cal_pts[i + 1]], fill=(31, 119, 180), width=2)
            for px, py in cal_pts:
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(31, 119, 180))

            ece = entry.get("calibrated", {}).get("expected_calibration_error", 0.0)
            draw.text((x0 + 10, y0 + 32), f"ECE={ece:.4f}", fill=(31, 119, 180), font=f_axis)

    out_p = Path(output_png)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_p)
    print(f"Saved reliability diagrams figure to {out_p}")


def generate_all_plots() -> None:
    plot_lead_time_skill()
    plot_provider_fusion_weights()
    plot_reliability_diagrams()


if __name__ == "__main__":
    generate_all_plots()
