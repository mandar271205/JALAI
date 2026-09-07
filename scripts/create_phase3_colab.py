"""Generate the directly runnable Phase-3 Google Colab notebook."""
from __future__ import annotations

import json
from pathlib import Path


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


cells = [
    markdown("""# JalRakshak Phase 3 - ConvLSTM Training

This notebook acquires/audits event-isolated GPM IMERG data, trains or resumes a compact ConvLSTM, evaluates Persistence, pySTEPS, and ConvLSTM on the same held-out event, and exports evidence. It never treats the 23-frame Phase-2 replay as a sufficient training corpus.

A deterministic checkpoint has no Brier/reliability metrics. `PHASE_3_MODEL_VALIDATED` remains false unless a real GPU run and held-out evaluation complete on an explicitly approved historical dataset."""),
    code("""# User configuration - no personal Drive path is hardcoded.
REPO_URL = ""                 # e.g. https://github.com/ORG/REPO.git; blank uses uploaded/current repo
REPO_BRANCH = "main"
WORK_DIR = "/content/jalrakshak-ml-starter"
CONFIG_PATH = "configs/training/convlstm_mumbai_v1.yaml"

USE_GOOGLE_DRIVE = False
DRIVE_OUTPUT_DIR = ""         # set after mounting, e.g. /content/drive/MyDrive/<your-folder>
ACQUIRE_DATA = False          # requires Earthdata credentials configured in ~/.netrc
RESUME_CHECKPOINT = ""        # blank starts a new run
ALLOW_CPU_SMOKE_TEST = False  # CPU mode is an engineering smoke test only
CONFIRM_DATASET_APPROVED_FOR_VALIDATION = False
"""),
    code("""# Optional clone/pull.
import os, subprocess
from pathlib import Path

if REPO_URL:
    work = Path(WORK_DIR)
    if (work / ".git").exists():
        subprocess.run(["git", "-C", str(work), "pull", "--ff-only"], check=True)
    else:
        subprocess.run(["git", "clone", "--branch", REPO_BRANCH, REPO_URL, str(work)], check=True)
    os.chdir(work)
elif not Path(CONFIG_PATH).exists():
    raise FileNotFoundError("Upload/open the repository or set REPO_URL before continuing.")

print("Repository:", Path.cwd())
"""),
    code("""# Colab already provides PyTorch. Install only runtime packages needed here.
%pip -q install zarr pyyaml pandas matplotlib pillow pysteps h5py requests
%pip -q install -e . --no-deps
"""),
    code("""# Mount Drive only when requested.
if USE_GOOGLE_DRIVE:
    from google.colab import drive
    drive.mount("/content/drive")
    if not DRIVE_OUTPUT_DIR:
        raise ValueError("Set DRIVE_OUTPUT_DIR after enabling USE_GOOGLE_DRIVE.")
"""),
    code("""import json, shutil
import torch
import yaml
from pathlib import Path

from jalrakshak_ml.deep_nowcast.acquisition import HistoricalDataAcquirer, audit_training_dataset
from jalrakshak_ml.deep_nowcast.dataset import build_datasets_from_config
from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.train import train_model
from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
from jalrakshak_ml.deep_nowcast.evaluate import evaluate_heldout
from jalrakshak_ml.deep_nowcast.visualize import (
    plot_forecast_comparison, plot_skill_report, plot_training_history, save_event_animation
)
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cpu" and not ALLOW_CPU_SMOKE_TEST:
    raise RuntimeError("No CUDA GPU detected. Enable a Colab GPU or set ALLOW_CPU_SMOKE_TEST=True.")
print("PyTorch:", torch.__version__, "Device:", DEVICE)
"""),
    code("""# Bounded acquisition is always planned before optional execution.
acquirer = HistoricalDataAcquirer(CONFIG_PATH)
plan = acquirer.plan()
display(plan)
if ACQUIRE_DATA:
    acquisition_result = acquirer.run(execute=True)
    display(acquisition_result["audit"])
else:
    print("Acquisition not executed. Existing versioned event stores will be used.")
"""),
    code("""# Audit the exact versioned corpus before constructing sequences.
with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
    cfg = yaml.safe_load(stream)
repo_root = Path(CONFIG_PATH).resolve().parents[2]
version_dir = repo_root / cfg["data"]["output_root"] / cfg["data"]["version"]
if not (version_dir / "manifest.json").exists():
    raise FileNotFoundError(
        f"No training manifest at {version_dir}. Set ACQUIRE_DATA=True after configuring Earthdata credentials."
    )
audit = audit_training_dataset(version_dir)
display(audit)
"""),
    code("""# Event-aware train/validation/test sequences and train-only normalization.
datasets, normalizer = build_datasets_from_config(CONFIG_PATH)
split_summary = {
    name: {"samples": len(ds), "events": list(ds.event_ids)} for name, ds in datasets.items()
}
display(split_summary)
assert normalizer.fitted_split == "train"
assert not (set(datasets["train"].event_ids) & set(datasets["validation"].event_ids))
assert not (set(datasets["train"].event_ids) & set(datasets["test"].event_ids))
assert not (set(datasets["validation"].event_ids) & set(datasets["test"].event_ids))
"""),
    code("""# Instantiate the compact deterministic ConvLSTM.
from torch.utils.data import DataLoader

seed = int(cfg["training"]["seed"])
generator = torch.Generator().manual_seed(seed)
batch_size = 1 if DEVICE == "cpu" else int(cfg["training"]["batch_size"])
train_loader = DataLoader(datasets["train"], batch_size=batch_size, shuffle=True, generator=generator)
validation_loader = DataLoader(datasets["validation"], batch_size=batch_size, shuffle=False)

model = ConvLSTMNowcaster(
    input_channels=len(cfg["dataset"]["input_channels"]),
    hidden_channels=cfg["model"]["hidden_channels"],
    num_layers=cfg["model"]["num_layers"],
    output_horizons=cfg["dataset"]["prediction_horizon"],
    output_channels=1,
    kernel_size=cfg["model"]["kernel_size"],
    head_channels=cfg["model"]["head_channels"],
)
print(model)
"""),
    code("""# Train or resume. CPU mode is intentionally restricted to one smoke epoch.
artifact_dir = repo_root / cfg["artifacts"]["model_dir"] / cfg["model"]["version"]
epochs = 1 if DEVICE == "cpu" else int(cfg["training"]["epochs"])
resume = Path(RESUME_CHECKPOINT) if RESUME_CHECKPOINT else None
loss_cfg = cfg["training"]["loss"]
scheduler_cfg = cfg["training"]["scheduler"]

outcome = train_model(
    model, train_loader, validation_loader,
    normalizer=normalizer,
    output_dir=artifact_dir,
    data_version=cfg["data"]["version"],
    model_version=cfg["model"]["version"],
    epochs=epochs,
    learning_rate=cfg["training"]["learning_rate"],
    weight_decay=cfg["training"]["weight_decay"],
    event_threshold_mm_h=loss_cfg["event_threshold_mm_h"],
    event_weight=loss_cfg["event_weight"],
    mse_weight=loss_cfg["mse_weight"],
    gradient_clip_norm=cfg["training"]["gradient_clip_norm"],
    early_stopping_patience=cfg["training"]["early_stopping_patience"],
    scheduler_patience=scheduler_cfg["patience"],
    scheduler_factor=scheduler_cfg["factor"],
    device=DEVICE,
    seed=seed,
    resume_from=resume,
)
display(outcome)
"""),
    code("""# Training/validation loss curve.
figure_dir = repo_root / cfg["artifacts"]["figure_dir"]
loss_plot = plot_training_history(outcome.history_json, figure_dir / "training_validation_loss.png")
display(loss_plot)
"""),
    code("""# Held-out evaluation: identical test samples for all three providers.
provider = ConvLSTMInference(outcome.best_checkpoint, device=DEVICE)
evaluation = evaluate_heldout(
    datasets["test"], provider,
    thresholds=[float(x) for x in cfg["evaluation"]["thresholds_mm_h"]],
)
evaluation_path = repo_root / cfg["artifacts"]["evaluation_report"]
evaluation_path.parent.mkdir(parents=True, exist_ok=True)
evaluation_path.write_text(json.dumps(evaluation, indent=2, allow_nan=False), encoding="utf-8")
display(evaluation)
"""),
    code("""# Actual / Persistence / pySTEPS / ConvLSTM / ConvLSTM error for one held-out sequence.
sample = datasets["test"].get_raw(0)
history = sample["inputs"][:, datasets["test"].input_channels.index("rainfall")]
actual = sample["target"][:, 0]
persistence_prediction = PersistenceNowcast().predict(history[-1], actual.shape[0])
pysteps_prediction = PystepsNowcast().predict(history, actual.shape[0])
convlstm_prediction = provider.predict(sample["inputs"], actual.shape[0])
comparison_plot = plot_forecast_comparison(
    actual, persistence_prediction, pysteps_prediction, convlstm_prediction,
    figure_dir / "heldout_forecast_comparison.png",
)
skill_plots = plot_skill_report(evaluation, figure_dir)
import zarr
test_record = next(item for item in datasets["test"].manifest["events"] if item["split"] == "test")
test_store = zarr.open(str(version_dir / test_record["path"]), mode="r")
animation_path = save_event_animation(
    test_store["rainfall"][:], [str(value) for value in test_store["time"][:]],
    figure_dir / "heldout_event.gif",
)
display(comparison_plot, *skill_plots, animation_path)
"""),
    code("""# Save checkpoint/results/plots to the user-selected Drive folder.
if USE_GOOGLE_DRIVE:
    destination = Path(DRIVE_OUTPUT_DIR)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artifact_dir, destination / artifact_dir.name, dirs_exist_ok=True)
    shutil.copytree(figure_dir, destination / "phase3_figures", dirs_exist_ok=True)
    shutil.copy2(evaluation_path, destination / evaluation_path.name)
    print("Exported to", destination)
"""),
    code("""# Validation status is evidence-based, never inferred from a smoke test.
PHASE_3_IMPLEMENTATION_READY = True
PHASE_3_MODEL_VALIDATED = bool(
    DEVICE == "cuda"
    and not ALLOW_CPU_SMOKE_TEST
    and CONFIRM_DATASET_APPROVED_FOR_VALIDATION
    and evaluation.get("status") == "COMPLETED"
    and outcome.best_checkpoint.exists()
)
print("PHASE_3_IMPLEMENTATION_READY=", PHASE_3_IMPLEMENTATION_READY)
print("PHASE_3_MODEL_VALIDATED=", PHASE_3_MODEL_VALIDATED)
if not PHASE_3_MODEL_VALIDATED:
    print("Model validation remains false until a genuine approved-data GPU run and held-out evaluation are complete.")
"""),
]

notebook = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"name": "01_convlstm_training.ipynb", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.x"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

output = Path("colab/01_convlstm_training.ipynb")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(output)
