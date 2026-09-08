"""Phase 4E Deep Nowcasting Tournament Runner.

Executes a scientifically fair, multi-seed tournament comparing:
- Persistence baseline
- PySTEPS (locked operational nowcaster)
- ConvLSTM V2 (Phase 3 baseline)
- ConvLSTM V3 (multi-source, multi-scale residual model)
- U-Net + ConvGRU (spatial encoder-decoder with temporal bottleneck)
- STAttentionNowcasterV1 (spatiotemporal patch & cross-time attention)
- Multi-seed deep ensembles

Under strict split isolation, anti-leakage, and common validation-first gates.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.losses import MultiScalePiecewiseLoss
from jalrakshak_ml.deep_nowcast.multisource_dataset import (
    MultiSourceNowcastDataset,
    MultiSourceStats,
)
from jalrakshak_ml.deep_nowcast.residual_convlstm import PersistenceResidualConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster
from jalrakshak_ml.evaluation.metrics import (
    compute_continuous_metrics,
    compute_dichotomous_metrics,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tournament")

THRESHOLDS = (0.1, 1.0, 5.0, 10.0)
SEEDS = (26071, 26072, 26073)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def evaluate_predictions(
    predictions: np.ndarray,  # [N, 4, 1, H, W]
    targets: np.ndarray,      # [N, 4, 1, H, W]
    masks: np.ndarray,        # [N, 4, 1, H, W]
) -> dict[str, Any]:
    """Calculate overall and per-horizon continuous and categorical metrics."""
    # Flatten across all horizons for overall metrics
    valid = masks.astype(bool) & np.isfinite(targets) & np.isfinite(predictions)
    obs_all = targets[valid]
    pred_all = predictions[valid]

    diff = pred_all - obs_all
    overall: dict[str, Any] = {
        "valid_pixels": int(obs_all.size),
        "mae": float(np.mean(np.abs(diff))) if obs_all.size else float("nan"),
        "rmse": float(np.sqrt(np.mean(diff**2))) if obs_all.size else float("nan"),
        "bias": float(np.mean(diff)) if obs_all.size else float("nan"),
    }
    for th in THRESHOLDS:
        dicho = compute_dichotomous_metrics(obs_all, pred_all, threshold=th)
        overall[f"pod_{th}"] = dicho["pod"]
        overall[f"far_{th}"] = dicho["far"]
        overall[f"csi_{th}"] = dicho["csi"]
        overall[f"f1_{th}"] = dicho["f1"]

    # Per lead horizon (+30, +60, +90, +120)
    by_lead: list[dict[str, Any]] = []
    horizons_min = [30, 60, 90, 120]
    for h_idx in range(4):
        h_targ = targets[:, h_idx]
        h_pred = predictions[:, h_idx]
        h_mask = masks[:, h_idx]
        h_val = h_mask.astype(bool) & np.isfinite(h_targ) & np.isfinite(h_pred)
        h_obs_flat = h_targ[h_val]
        h_pred_flat = h_pred[h_val]
        h_diff = h_pred_flat - h_obs_flat

        h_dict: dict[str, Any] = {
            "lead_step": h_idx + 1,
            "horizon_minutes": horizons_min[h_idx],
            "valid_pixels": int(h_obs_flat.size),
            "mae": float(np.mean(np.abs(h_diff))) if h_obs_flat.size else float("nan"),
            "rmse": float(np.sqrt(np.mean(h_diff**2))) if h_obs_flat.size else float("nan"),
            "bias": float(np.mean(h_diff)) if h_obs_flat.size else float("nan"),
        }
        for th in THRESHOLDS:
            dicho = compute_dichotomous_metrics(h_obs_flat, h_pred_flat, threshold=th)
            h_dict[f"pod_{th}"] = dicho["pod"]
            h_dict[f"far_{th}"] = dicho["far"]
            h_dict[f"csi_{th}"] = dicho["csi"]
            h_dict[f"f1_{th}"] = dicho["f1"]
        by_lead.append(h_dict)

    return {"overall": overall, "by_lead": by_lead}


def train_single_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    seed: int,
    epochs: int = 4,
    lr: float = 1e-3,
    device: str = "cpu",
    early_stopping_patience: int = 2,
    arch_name: str = "model",
) -> tuple[nn.Module, dict[str, Any]]:
    """Train a single model with early stopping on validation MAE."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    criterion = MultiScalePiecewiseLoss()

    best_val_mae = float("inf")
    best_weights = None
    patience_counter = 0
    history: list[dict[str, float]] = []

    start_time = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for batch in train_loader:
            inputs = batch["inputs"].to(device)
            persistence = batch["persistence_baseline"].to(device)
            target_phys = batch["target_physical"].to(device)
            target_mask = batch["target_mask"].to(device)
            missing_mask = batch["missing_channel_mask"].to(device)

            optimizer.zero_grad()
            pred = model(inputs, persistence, missing_channel_mask=missing_mask)
            loss = criterion(pred, target_phys, target_mask)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(loss.item())

        # Validation pass
        model.eval()
        val_preds, val_targets, val_masks = [], [], []
        with torch.no_grad():
            for batch in val_loader:
                inputs = batch["inputs"].to(device)
                persistence = batch["persistence_baseline"].to(device)
                missing_mask = batch["missing_channel_mask"].to(device)
                pred = model(inputs, persistence, missing_channel_mask=missing_mask)

                val_preds.append(pred.cpu().numpy())
                val_targets.append(batch["target_physical"].numpy())
                val_masks.append(batch["target_mask"].numpy())

        val_preds_arr = np.concatenate(val_preds, axis=0)
        val_targets_arr = np.concatenate(val_targets, axis=0)
        val_masks_arr = np.concatenate(val_masks, axis=0)

        val_metrics = evaluate_predictions(val_preds_arr, val_targets_arr, val_masks_arr)
        val_mae = val_metrics["overall"]["mae"]
        val_rmse = val_metrics["overall"]["rmse"]
        train_l_mean = float(np.mean(train_losses))

        log.info(
            "  [%s Seed %d] Epoch %d/%d - Train Loss: %.4f, Val MAE: %.4f, Val RMSE: %.4f",
            arch_name, seed, epoch, epochs, train_l_mean, val_mae, val_rmse
        )

        history.append({
            "epoch": epoch,
            "train_loss": train_l_mean,
            "val_mae": val_mae,
            "val_rmse": val_rmse,
        })


        if val_mae < best_val_mae:
            best_val_mae = val_mae
            best_weights = copy.deepcopy(model.state_dict())
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= early_stopping_patience:
                log.info("Early stopping triggered at epoch %d (best val MAE: %.4f)", epoch, best_val_mae)
                break

    duration = time.time() - start_time
    if best_weights is not None:
        model.load_state_dict(best_weights)

    return model, {
        "duration_seconds": duration,
        "epochs_trained": len(history),
        "best_val_mae": best_val_mae,
        "history": history,
    }


def run_tournament() -> dict[str, Any]:
    log.info("Starting Phase 4E Deep Nowcasting Model Tournament...")
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")

    # Ensure output model directories exist
    base_models_dir = Path("models/nowcast")
    (base_models_dir / "convlstm_v3").mkdir(parents=True, exist_ok=True)
    (base_models_dir / "unet_convgru_v1").mkdir(parents=True, exist_ok=True)
    (base_models_dir / "st_attention_nowcaster_v1").mkdir(parents=True, exist_ok=True)

    # 1. Prepare datasets under identical train-fitted statistics
    stats = MultiSourceStats.fit_from_training(version_dir, "")

    train_ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        stats=stats,
        dropout_prob=0.1,
    )
    val_ds = MultiSourceNowcastDataset(
        version_dir,
        split="validation",
        stats=stats,
        dropout_prob=0.0,
    )

    train_loader = DataLoader(train_ds, batch_size=4, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=4, shuffle=False)

    log.info("Loaded datasets: Train %d sequences, Validation %d sequences", len(train_ds), len(val_ds))

    # Define model factories
    architectures = {
        "convlstm_v3": lambda: ConvLSTMNowcasterV3(
            input_channels=3,
            hidden_channels=(24, 24),
            head_channels=16,
        ),
        "unet_convgru_v1": lambda: UNetConvGRUNowcaster(
            input_channels=3,
            base_channels=16,
            bottleneck_channels=48,
            head_channels=16,
        ),
        "st_attention_nowcaster_v1": lambda: STAttentionNowcasterV1(
            input_channels=3,
            embed_dim=64,
            num_heads=4,
            patch_size=8,
            head_channels=16,
        ),
    }

    # Track trained models, checkpoints, and validation outputs
    trained_checkpoints: dict[str, list[dict[str, Any]]] = {}
    validation_predictions_by_model_seed: dict[str, dict[int, np.ndarray]] = {}
    val_targets: np.ndarray | None = None
    val_masks: np.ndarray | None = None
    persistence_preds_val: np.ndarray | None = None
    gfs_preds_val: np.ndarray | None = None

    # Collect ground truth targets and baselines on validation
    v_preds_p, v_preds_gfs, v_targs, v_msks = [], [], [], []
    for batch in val_loader:
        p_base = batch["persistence_baseline"]  # [B, 1, H, W]
        # Repeat persistence across 4 horizons: [B, 4, 1, H, W]
        p_expanded = p_base.unsqueeze(1).repeat(1, 4, 1, 1, 1)
        v_preds_p.append(p_expanded.numpy())

        # GFS precipitation is channel 1 in inputs [B, 4, 3, H, W]
        gfs_raw = batch["inputs"][:, :, 1:2]  # [B, 4, 1, H, W]
        # Denormalize GFS back to physical mm/h
        gfs_phys = stats.denormalize_rainfall(gfs_raw)
        v_preds_gfs.append(gfs_phys.numpy() if isinstance(gfs_phys, np.ndarray) else gfs_phys.cpu().numpy())

        v_targs.append(batch["target_physical"].numpy())
        v_msks.append(batch["target_mask"].numpy())

    val_targets = np.concatenate(v_targs, axis=0)
    val_masks = np.concatenate(v_msks, axis=0)
    persistence_preds_val = np.concatenate(v_preds_p, axis=0)
    gfs_preds_val = np.concatenate(v_preds_gfs, axis=0)

    # 2. Train each architecture across the 3 mandatory seeds
    training_records: dict[str, Any] = {}
    for arch_name, factory in architectures.items():
        trained_checkpoints[arch_name] = []
        validation_predictions_by_model_seed[arch_name] = {}
        arch_records = []

        for seed in SEEDS:
            log.info("Training %s under Seed %d...", arch_name, seed)
            model = factory()
            param_count = sum(p.numel() for p in model.parameters())

            model, info = train_single_model(
                model=model,
                train_loader=train_loader,
                val_loader=val_loader,
                seed=seed,
                epochs=4,
                lr=1e-3,
                early_stopping_patience=2,
                arch_name=arch_name,
            )


            ckpt_path = base_models_dir / arch_name / f"checkpoint_seed_{seed}.pt"
            torch.save({
                "model_state": model.state_dict(),
                "config": model.config_dict(),
                "seed": seed,
                "training_info": info,
                "created_at": datetime.now(UTC).isoformat(),
            }, ckpt_path)

            sha256 = sha256_file(ckpt_path)
            ckpt_size = ckpt_path.stat().st_size

            # Evaluate on validation
            model.eval()
            val_preds_list = []
            with torch.no_grad():
                for batch in val_loader:
                    inputs = batch["inputs"]
                    p_base = batch["persistence_baseline"]
                    m_mask = batch["missing_channel_mask"]
                    out = model(inputs, p_base, missing_channel_mask=m_mask)
                    val_preds_list.append(out.cpu().numpy())
            val_preds_arr = np.concatenate(val_preds_list, axis=0)
            validation_predictions_by_model_seed[arch_name][seed] = val_preds_arr

            seed_metrics = evaluate_predictions(val_preds_arr, val_targets, val_masks)

            ckpt_meta = {
                "seed": seed,
                "checkpoint_path": str(ckpt_path).replace("\\", "/"),
                "sha256": sha256,
                "size_bytes": ckpt_size,
                "parameter_count": param_count,
                "training_duration_seconds": info["duration_seconds"],
                "epochs_trained": info["epochs_trained"],
                "val_mae": seed_metrics["overall"]["mae"],
                "val_rmse": seed_metrics["overall"]["rmse"],
                "val_csi_5": seed_metrics["overall"]["csi_5.0"],
                "metrics": seed_metrics,
            }
            trained_checkpoints[arch_name].append(ckpt_meta)
            arch_records.append(ckpt_meta)
            log.info("%s Seed %d -> Val MAE: %.4f, RMSE: %.4f", arch_name, seed, seed_metrics["overall"]["mae"], seed_metrics["overall"]["rmse"])

        training_records[arch_name] = arch_records

    # 3. Compile Validation Tournament Results
    log.info("Compiling Validation Tournament Report...")
    val_tournament_results: dict[str, Any] = {
        "evaluation_phase": "phase4e_validation_tournament",
        "timestamp": datetime.now(UTC).isoformat(),
        "split": "validation",
        "validation_event": "mumbai_monsoon_2023_07_25",
        "sequences_count": len(val_ds),
        "horizons": [30, 60, 90, 120],
        "models": {},
    }

    # Evaluate Baselines on Validation
    val_tournament_results["models"]["persistence"] = evaluate_predictions(
        persistence_preds_val, val_targets, val_masks
    )
    val_tournament_results["models"]["gfs"] = evaluate_predictions(
        gfs_preds_val, val_targets, val_masks
    )

    # Pull PySTEPS and ConvLSTM V2 validation metrics from locked Phase 4C report for exact parity
    p4c_val_path = Path("reports/phase4c_validation_evaluation.json")
    if p4c_val_path.exists():
        p4c_val = json.loads(p4c_val_path.read_text(encoding="utf-8"))
        if "pysteps" in p4c_val.get("models", {}):
            val_tournament_results["models"]["pysteps"] = p4c_val["models"]["pysteps"]
        if "convlstm_v2" in p4c_val.get("models", {}):
            val_tournament_results["models"]["convlstm_v2"] = p4c_val["models"]["convlstm_v2"]

    # Evaluate each neural architecture: per-seed and ensemble mean
    deep_model_summary: dict[str, dict[str, float]] = {}
    for arch_name in architectures:
        seeds_preds = [
            validation_predictions_by_model_seed[arch_name][s] for s in SEEDS
        ]
        # Ensemble mean across 3 seeds
        ens_pred = np.mean(seeds_preds, axis=0)
        ens_metrics = evaluate_predictions(ens_pred, val_targets, val_masks)

        val_tournament_results["models"][f"{arch_name}_ensemble"] = ens_metrics

        # Per seed metrics
        for s_meta in trained_checkpoints[arch_name]:
            seed = s_meta["seed"]
            val_tournament_results["models"][f"{arch_name}_seed{seed}"] = s_meta["metrics"]

        maes = [m["val_mae"] for m in trained_checkpoints[arch_name]]
        rmses = [m["val_rmse"] for m in trained_checkpoints[arch_name]]
        deep_model_summary[arch_name] = {
            "mean_mae": float(np.mean(maes)),
            "std_mae": float(np.std(maes)),
            "best_mae": float(np.min(maes)),
            "worst_mae": float(np.max(maes)),
            "ensemble_mae": ens_metrics["overall"]["mae"],
            "ensemble_rmse": ens_metrics["overall"]["rmse"],
            "ensemble_csi_5": ens_metrics["overall"]["csi_5.0"],
        }

    # Select Best Deep Model on Validation
    best_deep_model = min(deep_model_summary.keys(), key=lambda k: deep_model_summary[k]["ensemble_mae"])
    log.info("Validation Tournament Winner: %s (MAE: %.4f)", best_deep_model, deep_model_summary[best_deep_model]["ensemble_mae"])

    # 4. Run Ablation Study on the Validation Winner (Part P)
    log.info("Running Ablation Study on %s...", best_deep_model)
    ablation_configs = {
        "ablation_A_gpm_only": ["rainfall_gpm"],
        "ablation_B_gpm_plus_gfs_prate": ["rainfall_gpm", "gfs_precipitation"],
        "ablation_C_gpm_gfs_elevation": ["rainfall_gpm", "gfs_precipitation", "static_elevation"],
    }
    ablation_results: dict[str, Any] = {}
    for abl_key, chans in ablation_configs.items():
        abl_train_ds = MultiSourceNowcastDataset(
            version_dir, split="train", stats=stats, active_channels=chans, dropout_prob=0.0
        )
        abl_val_ds = MultiSourceNowcastDataset(
            version_dir, split="validation", stats=stats, active_channels=chans, dropout_prob=0.0
        )
        abl_train_ldr = DataLoader(abl_train_ds, batch_size=4, shuffle=True)
        abl_val_ldr = DataLoader(abl_val_ds, batch_size=4, shuffle=False)

        # Instantiate model with appropriate input channel count
        if best_deep_model == "convlstm_v3":
            abl_model = ConvLSTMNowcasterV3(input_channels=len(chans))
        elif best_deep_model == "unet_convgru_v1":
            abl_model = UNetConvGRUNowcaster(input_channels=len(chans))
        else:
            abl_model = STAttentionNowcasterV1(input_channels=len(chans))

        abl_model, _ = train_single_model(
            abl_model,
            abl_train_ldr,
            abl_val_ldr,
            seed=26071,
            epochs=3,
            lr=1e-3,
            early_stopping_patience=2,
            arch_name=abl_key,
        )

        abl_model.eval()
        abl_val_preds = []
        with torch.no_grad():
            for b in abl_val_ldr:
                out = abl_model(b["inputs"], b["persistence_baseline"], missing_channel_mask=b["missing_channel_mask"])
                abl_val_preds.append(out.cpu().numpy())
        abl_val_arr = np.concatenate(abl_val_preds, axis=0)
        abl_eval = evaluate_predictions(abl_val_arr, val_targets, val_masks)
        ablation_results[abl_key] = {
            "channels": chans,
            "overall_mae": abl_eval["overall"]["mae"],
            "overall_rmse": abl_eval["overall"]["rmse"],
            "csi_5": abl_eval["overall"]["csi_5.0"],
            "metrics": abl_eval,
        }
        log.info("Ablation %s -> Val MAE: %.4f", abl_key, abl_eval["overall"]["mae"])

    # 5. Run Source Dropout Study (Part Q)
    log.info("Running Source Dropout Study on %s...", best_deep_model)
    # Load primary seed 26071 model of the best architecture
    best_primary_model = architectures[best_deep_model]()
    best_ckpt = torch.load(base_models_dir / best_deep_model / "checkpoint_seed_26071.pt")
    best_primary_model.load_state_dict(best_ckpt["model_state"])
    best_primary_model.eval()

    dropout_scenarios = {
        "full_inputs": [False, False, False],
        "gfs_missing": [False, True, False],
        "elevation_missing": [False, False, True],
        "both_nwp_elevation_missing": [False, True, True],
    }
    dropout_results: dict[str, Any] = {}
    for sc_name, mask_spec in dropout_scenarios.items():
        fixed_mask = torch.tensor(mask_spec, dtype=torch.bool).unsqueeze(0)  # [1, 3]
        d_preds = []
        with torch.no_grad():
            for b in val_loader:
                inputs = b["inputs"]
                # Zero out masked channels in input
                b_mask = fixed_mask.repeat(inputs.shape[0], 1)
                out = best_primary_model(inputs, b["persistence_baseline"], missing_channel_mask=b_mask)
                d_preds.append(out.cpu().numpy())
        d_arr = np.concatenate(d_preds, axis=0)
        d_eval = evaluate_predictions(d_arr, val_targets, val_masks)
        dropout_results[sc_name] = {
            "mask": mask_spec,
            "overall_mae": d_eval["overall"]["mae"],
            "overall_rmse": d_eval["overall"]["rmse"],
            "mae_degradation_pct": (
                (d_eval["overall"]["mae"] - dropout_results["full_inputs"]["overall_mae"])
                / dropout_results["full_inputs"]["overall_mae"]
                * 100.0
                if "full_inputs" in dropout_results
                else 0.0
            ),
        }
        log.info("Dropout Scenario %s -> Val MAE: %.4f", sc_name, d_eval["overall"]["mae"])

    # 6. Model Freeze & Held-Out Test Tournament (Part R, S)
    log.info("Executing Single-Pass Held-Out Test Tournament across 51 sequences...")
    test_ds = MultiSourceNowcastDataset(
        version_dir, split="test", stats=stats, dropout_prob=0.0
    )
    test_loader = DataLoader(test_ds, batch_size=4, shuffle=False)

    # Collect ground truth on test
    t_preds_p, t_preds_gfs, t_targs, t_msks = [], [], [], []
    for batch in test_loader:
        p_base = batch["persistence_baseline"].unsqueeze(1).repeat(1, 4, 1, 1, 1)
        t_preds_p.append(p_base.numpy())

        gfs_raw = batch["inputs"][:, :, 1:2]
        gfs_phys = stats.denormalize_rainfall(gfs_raw)
        t_preds_gfs.append(gfs_phys.numpy() if isinstance(gfs_phys, np.ndarray) else gfs_phys.cpu().numpy())

        t_targs.append(batch["target_physical"].numpy())
        t_msks.append(batch["target_mask"].numpy())

    test_targets = np.concatenate(t_targs, axis=0)
    test_masks = np.concatenate(t_msks, axis=0)
    test_persistence = np.concatenate(t_preds_p, axis=0)
    test_gfs = np.concatenate(t_preds_gfs, axis=0)

    heldout_results: dict[str, Any] = {
        "evaluation_name": "phase4e_final_heldout_tournament",
        "timestamp": datetime.now(UTC).isoformat(),
        "total_test_events": 3,
        "total_test_samples": len(test_ds),
        "test_events": ["mumbai_monsoon_2023_08_24", "mumbai_monsoon_2024_08_04", "mumbai_monsoon_2024_09_05"],
        "models": {},
    }

    # Baselines on Test
    heldout_results["models"]["persistence"] = evaluate_predictions(
        test_persistence, test_targets, test_masks
    )
    heldout_results["models"]["gfs"] = evaluate_predictions(
        test_gfs, test_targets, test_masks
    )

    # Pull PySTEPS and ConvLSTM V2 test results from Phase 4C
    p4c_test_path = Path("reports/phase4c_final_heldout_evaluation.json")
    if p4c_test_path.exists():
        p4c_test = json.loads(p4c_test_path.read_text(encoding="utf-8"))
        if "pysteps" in p4c_test.get("models", {}):
            heldout_results["models"]["pysteps"] = p4c_test["models"]["pysteps"]
        if "convlstm_v2" in p4c_test.get("models", {}):
            heldout_results["models"]["convlstm_v2"] = p4c_test["models"]["convlstm_v2"]

    # Evaluate each neural model on Held-Out Test
    test_predictions_by_model: dict[str, list[np.ndarray]] = {}
    for arch_name, factory in architectures.items():
        test_predictions_by_model[arch_name] = []
        for seed in SEEDS:
            ckpt_path = base_models_dir / arch_name / f"checkpoint_seed_{seed}.pt"
            ckpt = torch.load(ckpt_path)
            eval_model = factory()
            eval_model.load_state_dict(ckpt["model_state"])
            eval_model.eval()

            t_preds_seed = []
            with torch.no_grad():
                for b in test_loader:
                    out = eval_model(b["inputs"], b["persistence_baseline"], missing_channel_mask=b["missing_channel_mask"])
                    t_preds_seed.append(out.cpu().numpy())
            t_preds_arr = np.concatenate(t_preds_seed, axis=0)
            test_predictions_by_model[arch_name].append(t_preds_arr)

            heldout_results["models"][f"{arch_name}_seed{seed}"] = evaluate_predictions(
                t_preds_arr, test_targets, test_masks
            )

        # Ensemble mean across the 3 seeds
        ens_test_pred = np.mean(test_predictions_by_model[arch_name], axis=0)
        heldout_results["models"][f"{arch_name}_ensemble"] = evaluate_predictions(
            ens_test_pred, test_targets, test_masks
        )
        log.info("Held-out %s Ensemble -> Test MAE: %.4f, RMSE: %.4f", arch_name, heldout_results["models"][f"{arch_name}_ensemble"]["overall"]["mae"], heldout_results["models"][f"{arch_name}_ensemble"]["overall"]["rmse"])

    # Compute Latency Benchmark
    log.info("Running Latency Benchmark...")
    benchmark_results: dict[str, Any] = {}
    dummy_input = torch.randn(1, 4, 3, 128, 128)
    dummy_p = torch.zeros(1, 1, 128, 128)
    dummy_mask = torch.zeros(1, 3, dtype=torch.bool)

    for arch_name, factory in architectures.items():
        m = factory()
        m.eval()
        # Warmup
        for _ in range(5):
            _ = m(dummy_input, dummy_p, missing_channel_mask=dummy_mask)

        # Benchmark 20 iterations
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            _ = m(dummy_input, dummy_p, missing_channel_mask=dummy_mask)
            times.append((time.perf_counter() - t0) * 1000.0)

        ckpt_file = base_models_dir / arch_name / "checkpoint_seed_26071.pt"
        benchmark_results[arch_name] = {
            "parameter_count": sum(p.numel() for p in m.parameters()),
            "checkpoint_size_kb": float(ckpt_file.stat().st_size / 1024.0),
            "mean_latency_ms": float(np.mean(times)),
            "std_latency_ms": float(np.std(times)),
            "p95_latency_ms": float(np.percentile(times, 95)),
        }

    # Model Selection Gate: Compare best deep model with PySTEPS
    pysteps_test_mae = heldout_results["models"].get("pysteps", {}).get("overall", {}).get("mae", 0.6465)
    pysteps_test_rmse = heldout_results["models"].get("pysteps", {}).get("overall", {}).get("rmse", 1.0355)
    best_deep_test_mae = heldout_results["models"][f"{best_deep_model}_ensemble"]["overall"]["mae"]
    best_deep_test_rmse = heldout_results["models"][f"{best_deep_model}_ensemble"]["overall"]["rmse"]

    deep_beats_pysteps = (best_deep_test_mae < pysteps_test_mae) and (best_deep_test_rmse < pysteps_test_rmse)
    operational_nowcaster = best_deep_model if deep_beats_pysteps else "PySTEPS"

    tournament_summary = {
        "validation_summary": deep_model_summary,
        "best_deep_model": best_deep_model,
        "operational_nowcaster": operational_nowcaster,
        "deep_beats_pysteps_overall": deep_beats_pysteps,
        "pysteps_heldout": {"mae": pysteps_test_mae, "rmse": pysteps_test_rmse},
        "best_deep_heldout": {"mae": best_deep_test_mae, "rmse": best_deep_test_rmse},
        "ablation_results": ablation_results,
        "dropout_results": dropout_results,
        "compute_benchmarks": benchmark_results,
        "training_records": training_records,
        "validation_tournament": val_tournament_results,
        "heldout_tournament": heldout_results,
    }

    # Save JSON artifacts
    Path("reports/phase4e_validation_tournament.json").write_text(
        json.dumps(val_tournament_results, indent=2), encoding="utf-8"
    )
    Path("reports/phase4e_final_heldout_tournament.json").write_text(
        json.dumps(heldout_results, indent=2), encoding="utf-8"
    )
    Path("reports/phase4e_compute_benchmark.json").write_text(
        json.dumps(benchmark_results, indent=2), encoding="utf-8"
    )

    log.info("Phase 4E Tournament completed successfully!")
    return tournament_summary


if __name__ == "__main__":
    run_tournament()
