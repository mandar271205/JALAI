import json
from pathlib import Path

def create_phase4e_notebook():
    nb = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Phase 4E: Advanced Deep Nowcasting Model Tournament (GPU Pipeline)\n",
                    "\n",
                    "**Pipeline:** JalRakshak AI (SIH26071) ML-GIS Research Pipeline  \n",
                    "**Phase:** 4E — Deep Neural Model Tournament  \n",
                    "**Execution Target:** Google Colab (CUDA GPU Accelerated)  \n",
                    "\n",
                    "---\n",
                    "\n",
                    "### Tournament Rules & Non-Leakage Guarantees:\n",
                    "1. **Identical Splits & Isolation:** Train, Validation, and Test events are permanently disjoint.\n",
                    "2. **Train-Only Normalization:** Normalization parameters (mean, std, percentiles) are strictly fitted on the TRAIN split only.\n",
                    "3. **Zero Test Contamination:** Hyperparameters, architecture comparisons, and early stopping decisions use VALIDATION only.\n",
                    "4. **Locked Test Gate:** The held-out TEST evaluation (`mumbai_monsoon_2023_08_24`, `mumbai_monsoon_2024_08_04`, `mumbai_monsoon_2024_09_05`) is guarded by `RUN_LOCKED_TEST = False` and can ONLY be unlocked manually after freezing the model selection.\n",
                    "5. **Authentic Data Only:** IMD Radar and MOSDAC INSAT are marked `REAL_DATA=false`. No synthetic radar/satellite data is ingested.\n",
                    "6. **Drive Persistence:** All models and reports are persisted to `/content/drive/MyDrive/JALAI_DATA/`.\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part A: Environment Setup & GPU Verification\n",
                    "Check for available CUDA hardware accelerator and configure environment."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part A: GPU Check & Environment Verification\n",
                    "import torch\n",
                    "import sys, os\n",
                    "\n",
                    "print(f\"Python Version: {sys.version}\")\n",
                    "print(f\"PyTorch Version: {torch.__version__}\")\n",
                    "gpu_available = torch.cuda.is_available()\n",
                    "print(f\"CUDA GPU Available: {gpu_available}\")\n",
                    "if gpu_available:\n",
                    "    print(f\"Device Name: {torch.cuda.get_device_name(0)}\")\n",
                    "    print(f\"Device Capability: {torch.cuda.get_device_capability(0)}\")\n",
                    "    DEVICE = \"cuda\"\n",
                    "else:\n",
                    "    print(\"WARNING: Running on CPU. Training will take longer. Consider selecting T4 GPU runtime.\")\n",
                    "    DEVICE = \"cpu\"\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part B: Repository Import & Dependency Installation\n",
                    "Clone or link the JalRakshak codebase and install required dependencies."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part B: Repository Import\n",
                    "import subprocess\n",
                    "from pathlib import Path\n",
                    "\n",
                    "REPO_URL = \"https://github.com/mandar271205/JALAI.git\"\n",
                    "REPO_BRANCH = \"main\"\n",
                    "WORK_DIR = Path(\"/content/JALAI/jalrakshak-ai\")\n",
                    "\n",
                    "if not WORK_DIR.exists():\n",
                    "    print(f\"Cloning {REPO_URL} (branch: {REPO_BRANCH})...\")\n",
                    "    subprocess.run([\"git\", \"clone\", \"--branch\", REPO_BRANCH, REPO_URL, \"/content/JALAI\"], check=True)\n",
                    "else:\n",
                    "    print(f\"Updating repository at {WORK_DIR}...\")\n",
                    "    subprocess.run([\"git\", \"-C\", \"/content/JALAI\", \"pull\", \"--ff-only\"], check=True)\n",
                    "\n",
                    "os.chdir(WORK_DIR)\n",
                    "print(f\"Working Directory: {Path.cwd()}\")\n",
                    "\n",
                    "# Install package in editable mode\n",
                    "subprocess.run([sys.executable, \"-m\", \"pip\", \"install\", \"-q\", \"-e\", \".\"], check=True)\n",
                    "print(\"JalRakshak package installed successfully.\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part C: Google Drive Mount & Directory Setup\n",
                    "Mount Google Drive for checkpoint persistence, preventing data loss across Colab sessions."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part C: Mount Google Drive\n",
                    "from google.colab import drive\n",
                    "\n",
                    "DRIVE_ROOT = Path(\"/content/drive/MyDrive/JALAI_DATA\")\n",
                    "DRIVE_GPM_DIR = DRIVE_ROOT / \"processed\" / \"training\" / \"gpm_imerg_v07_mumbai_monsoon_expanded_v1\"\n",
                    "DRIVE_RICH_GFS_DIR = DRIVE_ROOT / \"processed\" / \"gfs_replay\" / \"gfs_mumbai_phase4e_rich_non_test_v1\"\n",
                    "DRIVE_MODELS_DIR = DRIVE_ROOT / \"models\" / \"phase4e\"\n",
                    "DRIVE_REPORTS_DIR = DRIVE_ROOT / \"reports\" / \"phase4e\"\n",
                    "\n",
                    "print(\"Mounting Google Drive...\")\n",
                    "drive.mount(\"/content/drive\")\n",
                    "\n",
                    "DRIVE_MODELS_DIR.mkdir(parents=True, exist_ok=True)\n",
                    "DRIVE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)\n",
                    "print(f\"Persistent GPM Dir:      {DRIVE_GPM_DIR}\")\n",
                    "print(f\"Persistent Rich GFS Dir: {DRIVE_RICH_GFS_DIR}\")\n",
                    "print(f\"Persistent Models Dir:   {DRIVE_MODELS_DIR}\")\n",
                    "print(f\"Persistent Reports Dir:  {DRIVE_REPORTS_DIR}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part D: Verify Authentic Dataset & Channels Manifest\n",
                    "Inspect dataset files and confirm no fake radar or INSAT channels are configured."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part D: Verify Dataset & Multisource Manifest\n",
                    "import yaml\n",
                    "from jalrakshak_ml.config import load_yaml\n",
                    "\n",
                    "DATA_DIR = DRIVE_GPM_DIR if DRIVE_GPM_DIR.exists() else Path(\"data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1\")\n",
                    "MANIFEST_PATH = Path(\"configs/training/multisource_channels_v1.yaml\")\n",
                    "\n",
                    "assert DATA_DIR.exists(), f\"Dataset directory missing: {DATA_DIR}\"\n",
                    "assert MANIFEST_PATH.exists(), f\"Channels manifest missing: {MANIFEST_PATH}\"\n",
                    "\n",
                    "manifest = load_yaml(MANIFEST_PATH)\n",
                    "print(\"Active Multisource Channels:\")\n",
                    "for ch_name, ch_meta in manifest[\"channels\"].items():\n",
                    "    print(f\"  - {ch_name:24s} | Source: {ch_meta['source']:12s} | REAL_DATA: {ch_meta.get('REAL_DATA', False)}\")\n",
                    "\n",
                    "# Strictly verify unavailable channels are not claimed real\n",
                    "assert manifest[\"channels\"][\"radar_reflectivity\"][\"REAL_DATA\"] is False\n",
                    "assert manifest[\"channels\"][\"satellite_ir\"][\"REAL_DATA\"] is False\n",
                    "print(\"Verified: No synthetic radar or satellite observations used.\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part E: Verify Strict Train / Validation / Test Event Isolation (12/3/3 Split)\n",
                    "Ensure that all 18 event boundaries are strictly isolated and held-out test events are untouchable."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part E: Authoritative 18-Event Split Isolation\n",
                    "from jalrakshak_ml.deep_nowcast.splits import get_authoritative_splits\n",
                    "\n",
                    "splits = get_authoritative_splits()\n",
                    "train_events = set(splits.train)\n",
                    "val_events = set(splits.validation)\n",
                    "test_events = set(splits.test)\n",
                    "\n",
                    "print(f\"TRAIN Events ({len(train_events)}):      {sorted(train_events)}\")\n",
                    "print(f\"VALIDATION Events ({len(val_events)}): {sorted(val_events)}\")\n",
                    "print(f\"TEST Events (LOCKED) ({len(test_events)}): {sorted(test_events)}\")\n",
                    "\n",
                    "assert len(train_events) == 12, f\"Expected 12 train events, got {len(train_events)}\"\n",
                    "assert len(val_events) == 3, f\"Expected 3 validation events, got {len(val_events)}\"\n",
                    "assert len(test_events) == 3, f\"Expected 3 test events, got {len(test_events)}\"\n",
                    "\n",
                    "assert len(train_events.intersection(val_events)) == 0, \"Train and Val overlap!\"\n",
                    "assert len(train_events.intersection(test_events)) == 0, \"Train and Test overlap!\"\n",
                    "assert len(val_events.intersection(test_events)) == 0, \"Val and Test overlap!\"\n",
                    "assert \"mumbai_monsoon_2023_08_24\" in test_events\n",
                    "assert \"mumbai_monsoon_2024_08_04\" in test_events\n",
                    "assert \"mumbai_monsoon_2024_09_05\" in test_events\n",
                    "print(\"PASSED: Strict 12/3/3 event-level split isolation confirmed.\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part F: Fit / Load TRAIN-Only Normalization Statistics\n",
                    "Compute channel normalization statistics exclusively from the training split."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part F: Normalization fitted strictly on TRAIN\n",
                    "from jalrakshak_ml.deep_nowcast.multisource_dataset import MultiSourceStats\n",
                    "\n",
                    "stats = MultiSourceStats.fit_from_training(DATA_DIR, cache_path=DATA_DIR / \"multisource_train_stats.json\")\n",
                    "print(f\"Fitted Split: {stats.fitted_split} (Must be 'train')\")\n",
                    "assert stats.fitted_split == \"train\"\n",
                    "for ch, ch_s in stats.channel_stats.items():\n",
                    "    print(f\"  {ch:20s}: scale={ch_s.get('scale', 1.0):.4f}, center={ch_s.get('center', 0.0):.4f}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part G: Model 1 — ConvLSTM V3 (Seeds 26071, 26072, 26073)\n",
                    "Multi-source projection encoder + ConvLSTM temporal core + 4 lead-specific decoder heads + residual persistence connection."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part G: Train ConvLSTM V3 Across 3 Seeds\n",
                    "from jalrakshak_ml.deep_nowcast.tournament import train_model_seed\n",
                    "\n",
                    "SEEDS = [26071, 26072, 26073]\n",
                    "convlstm_results = {}\n",
                    "\n",
                    "for seed in SEEDS:\n",
                    "    ckpt_path = DRIVE_MODELS_DIR / f\"convlstm_v3_seed_{seed}.pt\"\n",
                    "    print(f\"=== Training ConvLSTM V3 (Seed {seed}) ===\")\n",
                    "    res = train_model_seed(\n",
                    "        model_key=\"convlstm_v3\",\n",
                    "        config_path=\"configs/training/convlstm_v3.yaml\",\n",
                    "        seed=seed,\n",
                    "        device=DEVICE,\n",
                    "        output_checkpoint=ckpt_path,\n",
                    "    )\n",
                    "    convlstm_results[seed] = res\n",
                    "    print(f\"ConvLSTM V3 Seed {seed} Finished: Val MAE: {res['best_val_mae']:.4f}, Val RMSE: {res['best_val_rmse']:.4f}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part H: Model 2 — U-Net + ConvGRU (Seeds 26071, 26072, 26073)\n",
                    "Multi-scale spatial encoder-decoder with skip connections + ConvGRU spatiotemporal bottleneck at 32x32 + 4 lead heads."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part H: Train U-Net + ConvGRU Across 3 Seeds\n",
                    "unet_results = {}\n",
                    "\n",
                    "for seed in SEEDS:\n",
                    "    ckpt_path = DRIVE_MODELS_DIR / f\"unet_convgru_v1_seed_{seed}.pt\"\n",
                    "    print(f\"=== Training U-Net + ConvGRU (Seed {seed}) ===\")\n",
                    "    res = train_model_seed(\n",
                    "        model_key=\"unet_convgru_v1\",\n",
                    "        config_path=\"configs/training/unet_convgru_v1.yaml\",\n",
                    "        seed=seed,\n",
                    "        device=DEVICE,\n",
                    "        output_checkpoint=ckpt_path,\n",
                    "    )\n",
                    "    unet_results[seed] = res\n",
                    "    print(f\"U-Net + ConvGRU Seed {seed} Finished: Val MAE: {res['best_val_mae']:.4f}, Val RMSE: {res['best_val_rmse']:.4f}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part I: Model 3 — Spatiotemporal Attention (Seeds 26071, 26072, 26073)\n",
                    "Compact patch vision transformer (8x8 patches) with spatial self-attention + cross-time attention + 4 lead-specific reconstruction heads."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part I: Train STAttentionNowcasterV1 Across 3 Seeds\n",
                    "st_attn_results = {}\n",
                    "\n",
                    "for seed in SEEDS:\n",
                    "    ckpt_path = DRIVE_MODELS_DIR / f\"st_attention_nowcaster_v1_seed_{seed}.pt\"\n",
                    "    print(f\"=== Training STAttention (Seed {seed}) ===\")\n",
                    "    res = train_model_seed(\n",
                    "        model_key=\"st_attention_nowcaster_v1\",\n",
                    "        config_path=\"configs/training/st_attention_nowcaster_v1.yaml\",\n",
                    "        seed=seed,\n",
                    "        device=DEVICE,\n",
                    "        output_checkpoint=ckpt_path,\n",
                    "    )\n",
                    "    st_attn_results[seed] = res\n",
                    "    print(f\"STAttention Seed {seed} Finished: Val MAE: {res['best_val_mae']:.4f}, Val RMSE: {res['best_val_rmse']:.4f}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part J: Validation-Only Tournament Evaluation & Ranking\n",
                    "Evaluate all architectures and baselines (Persistence, PySTEPS, ConvLSTM V2, ConvLSTM V3, U-Net ConvGRU, ST Attention) exclusively on VALIDATION data."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part J: Validation Tournament Evaluation\n",
                    "from jalrakshak_ml.deep_nowcast.tournament import run_validation_tournament\n",
                    "\n",
                    "val_tournament_json = DRIVE_REPORTS_DIR / \"phase4e_validation_tournament.json\"\n",
                    "val_summary = run_validation_tournament(\n",
                    "    models_dir=DRIVE_MODELS_DIR,\n",
                    "    output_json=val_tournament_json,\n",
                    "    device=DEVICE,\n",
                    ")\n",
                    "\n",
                    "print(\"=== VALIDATION TOURNAMENT SUMMARY ===\")\n",
                    "for rank, item in enumerate(val_summary[\"ranking\"], 1):\n",
                    "    print(f\"{rank}. {item['model_key']:25s} | Val MAE: {item['overall_mae']:.4f} | RMSE: {item['overall_rmse']:.4f} | CSI>=5: {item.get('csi_5', 0.0):.4f}\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part K: Input Channel Ablation Study (Validation Only)\n",
                    "Ablate inputs on the validation-winning neural architecture:\n",
                    "- Configuration A: GPM Precipitation Only\n",
                    "- Configuration B: GPM + GFS Precipitation\n",
                    "- Configuration C: Full Multi-Source Set (GPM + GFS + DEM)"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part K: Ablation Study\n",
                    "from jalrakshak_ml.deep_nowcast.tournament import run_ablation_study\n",
                    "\n",
                    "winner_key = val_summary[\"ranking\"][0][\"model_key\"]\n",
                    "print(f\"Running Ablation Study on Validation Winner: {winner_key}...\")\n",
                    "ablation_json = DRIVE_REPORTS_DIR / \"phase4e_ablation_results.json\"\n",
                    "ablation_res = run_ablation_study(\n",
                    "    best_model_key=winner_key,\n",
                    "    models_dir=DRIVE_MODELS_DIR,\n",
                    "    output_json=ablation_json,\n",
                    "    device=DEVICE,\n",
                    ")\n",
                    "print(\"Ablation Study Complete. Results saved to Drive.\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part L: Operational Source Dropout & Fault Tolerance Evaluation\n",
                    "Measure degradation under dropped GFS, dropped DEM, and pure observation fallback."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part L: Source Dropout Study\n",
                    "from jalrakshak_ml.deep_nowcast.tournament import run_source_dropout_study\n",
                    "\n",
                    "dropout_json = DRIVE_REPORTS_DIR / \"phase4e_source_dropout_results.json\"\n",
                    "dropout_res = run_source_dropout_study(\n",
                    "    best_model_key=winner_key,\n",
                    "    models_dir=DRIVE_MODELS_DIR,\n",
                    "    output_json=dropout_json,\n",
                    "    device=DEVICE,\n",
                    ")\n",
                    "print(\"Source Dropout Study Complete. Results saved to Drive.\")\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part M & N: Model Selection Freeze & SHA-256 Checksum Hashing\n",
                    "Freeze hyperparameters, architecture, and compute SHA-256 hashes of all winner checkpoints."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part M & N: Model Selection Freeze & Hashing\n",
                    "import hashlib\n",
                    "from datetime import datetime, UTC\n",
                    "\n",
                    "frozen_manifest = {\n",
                    "    \"timestamp\": datetime.now(UTC).isoformat(),\n",
                    "    \"best_deep_model\": winner_key,\n",
                    "    \"validation_mae\": val_summary[\"ranking\"][0][\"overall_mae\"],\n",
                    "    \"validation_rmse\": val_summary[\"ranking\"][0][\"overall_rmse\"],\n",
                    "    \"checkpoint_hashes\": {},\n",
                    "    \"selection_frozen\": True\n",
                    "}\n",
                    "\n",
                    "for pt in DRIVE_MODELS_DIR.glob(\"*.pt\"):\n",
                    "    h = hashlib.sha256(pt.read_bytes()).hexdigest()\n",
                    "    frozen_manifest[\"checkpoint_hashes\"][pt.name] = f\"sha256:{h}\"\n",
                    "\n",
                    "freeze_path = DRIVE_REPORTS_DIR / \"phase4e_frozen_selection.json\"\n",
                    "freeze_path.write_text(json.dumps(frozen_manifest, indent=2), encoding=\"utf-8\")\n",
                    "print(f\"MODEL SELECTION FROZEN! Manifest written to: {freeze_path}\")\n",
                    "print(json.dumps(frozen_manifest, indent=2))\n"
                ]
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Part O: LOCKED HELD-OUT TEST EVALUATION (EXPLICIT GUARD)\n",
                    "\n",
                    "### IMPORTANT SAFETY GUARD:\n",
                    "- `RUN_LOCKED_TEST = False` by default.\n",
                    "- This cell **MUST NOT** execute automatically during training or hyperparameter searches.\n",
                    "- To execute held-out test evaluation, manually set `RUN_LOCKED_TEST = True` below **ONLY AFTER** Part M/N model selection has been frozen."
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# Part O: LOCKED HELD-OUT TEST EVALUATION\n",
                    "# ==========================================================================\n",
                    "# MANUAL SAFETY GUARD: Set to True ONLY after reviewing validation results\n",
                    "# and confirming frozen model selection in Part M.\n",
                    "# ==========================================================================\n",
                    "RUN_LOCKED_TEST = False\n",
                    "# ==========================================================================\n",
                    "\n",
                    "if not RUN_LOCKED_TEST:\n",
                    "    print(\"LOCKED TEST EVALUATION SKIPPED.\")\n",
                    "    print(\"To unlock the held-out test tournament, change RUN_LOCKED_TEST = True and re-run this cell.\")\n",
                    "else:\n",
                    "    print(\"UNLOCKING HELD-OUT TEST TOURNAMENT EVALUATION...\")\n",
                    "    from jalrakshak_ml.deep_nowcast.tournament import run_heldout_test_tournament\n",
                    "    \n",
                    "    test_tournament_json = DRIVE_REPORTS_DIR / \"phase4e_final_heldout_tournament.json\"\n",
                    "    test_summary = run_heldout_test_tournament(\n",
                    "        models_dir=DRIVE_MODELS_DIR,\n",
                    "        frozen_manifest=frozen_manifest,\n",
                    "        output_json=test_tournament_json,\n",
                    "        device=DEVICE,\n",
                    "    )\n",
                    "    print(\"=== HELD-OUT TEST TOURNAMENT COMPLETE ===\")\n",
                    "    for rank, item in enumerate(test_summary[\"ranking\"], 1):\n",
                    "        print(f\"{rank}. {item['model_key']:25s} | Test MAE: {item['overall_mae']:.4f} | RMSE: {item['overall_rmse']:.4f}\")\n"
                ]
            }
        ],
        "metadata": {
            "accelerator": "GPU",
            "colab": {
                "provenance": []
            },
            "kernelspec": {
                "display_name": "Python 3",
                "name": "python3"
            },
            "language_info": {
                "name": "python"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 0
    }
    
    out_file = Path("colab/02_phase4e_deep_model_tournament.ipynb")
    out_file.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"Created Colab notebook: {out_file} ({out_file.stat().st_size} bytes)")

if __name__ == "__main__":
    create_phase4e_notebook()
