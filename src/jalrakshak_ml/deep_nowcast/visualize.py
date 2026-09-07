"""Phase-3 training and held-out forecast visualizations."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation


def plot_training_history(history: str | Path | list[dict], output_path: str | Path) -> Path:
    if isinstance(history, (str, Path)):
        history = json.loads(Path(history).read_text(encoding="utf-8"))
    epochs = [row["epoch"] for row in history]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(epochs, [row["train_loss"] for row in history], marker="o", label="Train")
    ax.plot(epochs, [row["validation_loss"] for row in history], marker="o", label="Validation")
    ax.set(xlabel="Epoch", ylabel="Weighted normalized loss", title="ConvLSTM Training History")
    ax.grid(alpha=0.3)
    ax.legend()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_forecast_comparison(
    observation: np.ndarray,
    persistence: np.ndarray,
    pysteps: np.ndarray,
    convlstm: np.ndarray,
    output_path: str | Path,
) -> Path:
    arrays = [observation, persistence, pysteps, convlstm]
    if any(np.asarray(value).shape != np.asarray(observation).shape for value in arrays):
        raise ValueError("All forecast comparison arrays must share [horizon,H,W] shape")
    horizons = observation.shape[0]
    vmax = max(1.0, float(np.nanpercentile(np.concatenate([a.ravel() for a in arrays]), 99)))
    fig, axes = plt.subplots(horizons, 5, figsize=(18, 3.4 * horizons), squeeze=False)
    titles = ["Actual", "Persistence", "PySTEPS", "ConvLSTM", "ConvLSTM Error"]
    for lead in range(horizons):
        values = [
            observation[lead], persistence[lead], pysteps[lead], convlstm[lead],
            convlstm[lead] - observation[lead],
        ]
        for col, value in enumerate(values):
            if col < 4:
                image = axes[lead, col].imshow(value, cmap="Blues", vmin=0, vmax=vmax)
            else:
                limit = max(1.0, float(np.nanpercentile(np.abs(value), 99)))
                image = axes[lead, col].imshow(value, cmap="coolwarm", vmin=-limit, vmax=limit)
            axes[lead, col].set_title(f"{titles[col]} (+{(lead + 1) * 30} min)")
            axes[lead, col].axis("off")
            fig.colorbar(image, ax=axes[lead, col], fraction=0.046, pad=0.03)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_skill_report(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    providers = report["providers"]
    lead_path = output_dir / "skill_vs_lead_time.png"
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for name, payload in providers.items():
        metrics = payload["metrics"]
        x = [row["horizon_minutes"] for row in metrics]
        axes[0].plot(x, [row["mae"] for row in metrics], marker="o", label=name)
        axes[1].plot(x, [row["csi_1.0"] for row in metrics], marker="o", label=name)
    axes[0].set(xlabel="Lead time (minutes)", ylabel="MAE (mm/h)", title="MAE vs Lead Time")
    axes[1].set(xlabel="Lead time (minutes)", ylabel="CSI", title="CSI at 1.0 mm/h")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend()
    fig.tight_layout()
    fig.savefig(lead_path, dpi=160)
    plt.close(fig)

    threshold_path = output_dir / "threshold_skill_comparison.png"
    thresholds = [str(value) for value in report["thresholds_mm_h"]]
    names = list(providers)
    width = 0.8 / len(names)
    x = np.arange(len(thresholds))
    fig, ax = plt.subplots(figsize=(9, 5))
    for index, name in enumerate(names):
        final_lead = providers[name]["metrics"][-1]
        values = [final_lead[f"csi_{threshold}"] or 0.0 for threshold in thresholds]
        ax.bar(x + index * width, values, width=width, label=name)
    ax.set_xticks(x + width * (len(names) - 1) / 2, thresholds)
    ax.set(xlabel="Rainfall threshold (mm/h)", ylabel="CSI", title="Threshold Skill at +120 Minutes")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(threshold_path, dpi=160)
    plt.close(fig)
    return lead_path, threshold_path


def save_event_animation(
    rainfall: np.ndarray,
    times: list[str],
    output_path: str | Path,
    interval_ms: int = 300,
) -> Path:
    if rainfall.ndim != 3 or rainfall.shape[0] != len(times):
        raise ValueError("rainfall and times must align as [time,H,W]")
    fig, ax = plt.subplots(figsize=(6, 6))
    vmax = max(1.0, float(np.nanpercentile(rainfall, 99)))
    image = ax.imshow(rainfall[0], cmap="Blues", vmin=0, vmax=vmax)
    title = ax.set_title(times[0])
    ax.axis("off")

    def update(index):
        image.set_array(rainfall[index])
        title.set_text(times[index])
        return image, title

    movie = animation.FuncAnimation(fig, update, frames=len(times), interval=interval_ms, blit=True)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".gif":
        movie.save(output_path, writer="pillow")
    else:
        movie.save(output_path)
    plt.close(fig)
    return output_path
