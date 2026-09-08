"""Generate the isolated Phase-3 V2 Colab training notebook."""
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
    markdown("""# JalRakshak Phase 3 V2 - Heavy-Rain Persistence-Residual ConvLSTM

This notebook trains `convlstm_mumbai_heavyrain_v2` on the existing 432-frame expanded GPM corpus. It never downloads data, never selects a checkpoint using test data, and never starts Phase 4. V2 remains unvalidated until this GPU run and the final held-out evaluation complete successfully."""),
    code("""# Cell 1: user paths. The expanded dataset must already exist.
REPO_URL = ""                 # Optional Git URL; blank uses the current/uploaded repository
REPO_BRANCH = "main"
WORK_DIR = "/content/jalrakshak-ml-starter"
CONFIG_PATH = "configs/training/convlstm_mumbai_heavyrain_v2.yaml"
DRIVE_DATASET_DIR = ""        # Optional Drive path to the expanded_v1 directory
DRIVE_OUTPUT_DIR = ""         # Optional Drive folder for checkpoints/reports
RESUME_CHECKPOINT = ""        # Optional V2 latest.pt path
"""),
    code("""# Cell 2: clone/open repository and optionally mount Drive.
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
    raise FileNotFoundError("Upload/open the repository or set REPO_URL.")

if DRIVE_DATASET_DIR or DRIVE_OUTPUT_DIR:
    from google.colab import drive
    drive.mount("/content/drive")
print("Repository:", Path.cwd())
"""),
    code("""# Cell 3: install runtime dependencies. No data acquisition occurs.
%pip -q install zarr pyyaml pandas matplotlib pillow pysteps h5py requests
%pip -q install -e . --no-deps
"""),
    code("""# Cell 4: require a real CUDA runtime.
import torch
if not torch.cuda.is_available():
    raise RuntimeError("Select Runtime > Change runtime type > GPU before training V2.")
print("PyTorch:", torch.__version__)
print("GPU:", torch.cuda.get_device_name(0))
"""),
    code("""# Cell 5: mount/link the existing expanded corpus and audit its identity.
import json, yaml
from jalrakshak_ml.deep_nowcast.acquisition import audit_training_dataset

with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
    cfg = yaml.safe_load(stream)
repo_root = Path(CONFIG_PATH).resolve().parents[2]
version_dir = repo_root / cfg["data"]["output_root"] / cfg["data"]["version"]
if not version_dir.exists() and DRIVE_DATASET_DIR:
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    version_dir.symlink_to(Path(DRIVE_DATASET_DIR), target_is_directory=True)
if not (version_dir / "manifest.json").exists():
    raise FileNotFoundError(
        f"Missing existing expanded dataset at {version_dir}. Set DRIVE_DATASET_DIR; do not reacquire it."
    )
audit = audit_training_dataset(version_dir)
if audit["total_frames"] != 432:
    raise RuntimeError(f"Expected 432 GPM frames, found {audit['total_frames']}")
display(audit)
"""),
    code("""# Cell 6: verify event isolation and train-only oversampling.
from torch.utils.data import SequentialSampler, WeightedRandomSampler
from jalrakshak_ml.deep_nowcast.dataset import build_dataloaders, build_datasets_from_config

datasets, normalizer = build_datasets_from_config(CONFIG_PATH)
loaders, sampling = build_dataloaders(datasets, cfg["training"])
assert isinstance(loaders["train"].sampler, WeightedRandomSampler)
assert isinstance(loaders["validation"].sampler, SequentialSampler)
assert isinstance(loaders["test"].sampler, SequentialSampler)
split_summary = {
    split: {"samples": len(dataset), "events": list(dataset.event_ids)}
    for split, dataset in datasets.items()
}
display(split_summary)
display({key: value for key, value in sampling.items() if key != "sequence_maxima_mm_h"})
"""),
    code("""# Cell 7: train or resume V2. best.pt is selected only by validation score.
import sys

train_command = [
    sys.executable,
    "scripts/train_convlstm.py",
    "--config", CONFIG_PATH,
    "--device", "cuda",
]
if RESUME_CHECKPOINT:
    train_command.extend(["--resume", RESUME_CHECKPOINT])
print("Running:", " ".join(train_command))
subprocess.run(train_command, check=True)
"""),
    code("""# Cell 8: inspect checkpoint-selection evidence before touching the test split.
model_dir = repo_root / cfg["artifacts"]["model_dir"] / cfg["model"]["version"]
metadata_path = model_dir / "training_metadata.json"
training_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
display({
    "best_epoch": training_metadata["best_epoch"],
    "best_validation_score": training_metadata["best_validation_score"],
    "best_validation_metrics": training_metadata["best_validation_metrics"],
    "checkpoint": training_metadata["best_checkpoint"],
    "sha256": training_metadata["best_checkpoint_sha256"],
})
"""),
    code("""# Cell 9: one final, mask-aware three-way evaluation on the untouched test split.
checkpoint = model_dir / "best.pt"
evaluation_command = [
    sys.executable,
    "scripts/evaluate_phase3.py",
    "--config", CONFIG_PATH,
    "--checkpoint", str(checkpoint),
    "--device", "cuda",
]
print("Running:", " ".join(evaluation_command))
subprocess.run(evaluation_command, check=True)
evaluation_path = repo_root / cfg["artifacts"]["evaluation_report"]
evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
display(evaluation)
"""),
    code("""# Cell 10: optionally export immutable evidence to Drive.
import shutil
if DRIVE_OUTPUT_DIR:
    destination = Path(DRIVE_OUTPUT_DIR)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(model_dir, destination / model_dir.name, dirs_exist_ok=True)
    shutil.copy2(evaluation_path, destination / evaluation_path.name)
    print("Exported to", destination)
"""),
    code("""# Cell 11: status gate. Do not promote V2 automatically.
PHASE_2_READY = True
PHASE_3_IMPLEMENTATION_READY = True
PHASE_3_GPU_PIPELINE_VERIFIED = True
PHASE_3_V2_IMPLEMENTATION_READY = True
PHASE_3_MODEL_VALIDATED = False  # requires scientific review of this held-out result
PHASE_4_STARTED = False
print({name: value for name, value in globals().items() if name.startswith("PHASE_")})
"""),
]

notebook = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"name": "02_convlstm_heavyrain_v2_training.ipynb", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.x"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

output = Path("colab/02_convlstm_heavyrain_v2_training.ipynb")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(output)
