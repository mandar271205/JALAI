"""Supervised training script for learned multi-model fusion gating network.

Trains a compact PyTorch MLP on the authentic Train split (mumbai_monsoon_2023_07_18)
and validates on the Validation split (mumbai_monsoon_2023_07_25).
Held-out test split is STRICTLY untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import yaml

from jalrakshak_ml.fusion.dataset import FusionDataset
from jalrakshak_ml.fusion.gating import LearnedGateMLP


def set_seed(seed: int = 26071) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train_learned_gate(
    train_dataset_dir: str | Path = "data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
    gfs_replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_non_test_replay_v1",
    model_output_dir: str | Path = "models/fusion/learned_gate_v1",
    config_output_path: str | Path = "configs/fusion/learned_gate_v1.yaml",
    report_output_path: str | Path = "reports/phase4c_learned_gate_training.md",
    seed: int = 26071,
    epochs: int = 40,
    lr: float = 0.005,
    weight_decay: float = 1e-4,
    device: str = "cpu",
) -> dict[str, Any]:
    """Train compact MLP gate minimizing spatial MAE on Train split."""
    set_seed(seed)
    dev = torch.device(device)

    print("Loading Train split...")
    ds_train = FusionDataset("train", gpm_dataset_dir=train_dataset_dir, gfs_replay_root=gfs_replay_root)
    X_tr_np, Y_preds_tr_np, Y_tr_np, Mask_tr_np = ds_train.get_tabular_data()

    print("Loading Validation split...")
    ds_val = FusionDataset("validation", gpm_dataset_dir=train_dataset_dir, gfs_replay_root=gfs_replay_root)
    X_val_np, Y_preds_val_np, Y_val_np, Mask_val_np = ds_val.get_tabular_data()

    providers = ds_train.expected_providers  # ("persistence", "pysteps", "convlstm_v2", "gfs")
    p_to_idx = {p: i for i, p in enumerate(providers)}

    # Standardize input features using strictly Train split statistics (no test or val leakage)
    X_mean = np.mean(X_tr_np, axis=0, keepdims=True)
    X_std = np.std(X_tr_np, axis=0, keepdims=True)
    X_std[X_std < 1e-6] = 1.0

    X_tr_norm = np.nan_to_num((X_tr_np - X_mean) / X_std, nan=0.0, posinf=0.0, neginf=0.0)
    X_val_norm = np.nan_to_num((X_val_np - X_mean) / X_std, nan=0.0, posinf=0.0, neginf=0.0)

    # Convert to tensors
    X_tr = torch.from_numpy(X_tr_norm.astype(np.float32)).to(dev)
    Y_tr = torch.from_numpy(Y_tr_np).to(dev)
    Mask_tr = torch.from_numpy(Mask_tr_np).to(dev)
    Preds_tr = torch.stack([torch.from_numpy(Y_preds_tr_np[p]).to(dev) for p in providers], dim=1)  # [N, P, Y, X]

    X_val = torch.from_numpy(X_val_norm.astype(np.float32)).to(dev)
    Y_val = torch.from_numpy(Y_val_np).to(dev)
    Mask_val = torch.from_numpy(Mask_val_np).to(dev)
    Preds_val = torch.stack([torch.from_numpy(Y_preds_val_np[p]).to(dev) for p in providers], dim=1)  # [N, P, Y, X]

    # Availability mask: persistence, pysteps, and gfs are available; convlstm_v2 is unavailable
    avail_mask_tr = torch.tensor(
        [[p != "convlstm_v2" for p in providers]], dtype=torch.bool, device=dev
    ).repeat(X_tr.shape[0], 1)
    avail_mask_val = torch.tensor(
        [[p != "convlstm_v2" for p in providers]], dtype=torch.bool, device=dev
    ).repeat(X_val.shape[0], 1)

    model = LearnedGateMLP(in_features=X_tr.shape[1], num_providers=len(providers), hidden_dim=32).to(dev)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

    best_val_mae = float("inf")
    best_weights_summary: dict[str, float] = {}
    best_state: dict[str, Any] = {}
    best_epoch = 0
    history = []

    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()

        # [N, P] weights
        weights_tr = model(X_tr, availability_mask=avail_mask_tr)
        # Reshape to [N, P, 1, 1] for broadcasting across [N, P, Y, X]
        w_expanded = weights_tr.unsqueeze(-1).unsqueeze(-1)
        fused_tr = torch.sum(w_expanded * Preds_tr, dim=1)  # [N, Y, X]

        # Spatial MAE over valid cells
        abs_err_tr = torch.abs(fused_tr - Y_tr)
        loss = torch.sum(abs_err_tr * Mask_tr) / torch.clamp(torch.sum(Mask_tr), min=1.0)

        loss.backward()
        optimizer.step()

        # Validation evaluation
        model.eval()
        with torch.no_grad():
            weights_val = model(X_val, availability_mask=avail_mask_val)
            w_val_exp = weights_val.unsqueeze(-1).unsqueeze(-1)
            fused_val = torch.sum(w_val_exp * Preds_val, dim=1)

            abs_err_val = torch.abs(fused_val - Y_val)
            val_mae = (torch.sum(abs_err_val * Mask_val) / torch.clamp(torch.sum(Mask_val), min=1.0)).item()
            sq_err_val = (fused_val - Y_val) ** 2
            val_rmse = torch.sqrt(torch.sum(sq_err_val * Mask_val) / torch.clamp(torch.sum(Mask_val), min=1.0)).item()

            mean_w = weights_val.mean(dim=0).cpu().numpy()
            w_dict = {providers[i]: float(mean_w[i]) for i in range(len(providers))}

        history.append({
            "epoch": epoch,
            "train_mae": float(loss.item()),
            "val_mae": float(val_mae),
            "val_rmse": float(val_rmse),
            "mean_weights": w_dict,
        })

        if val_mae < best_val_mae:
            best_val_mae = val_mae
            best_epoch = epoch
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            best_weights_summary = w_dict

        if epoch % 5 == 0 or epoch == epochs:
            print(
                f"Epoch {epoch:02d}/{epochs} | Train MAE: {loss.item():.4f} | "
                f"Val MAE: {val_mae:.4f} | Val RMSE: {val_rmse:.4f} | "
                f"W: PySTEPS={w_dict['pysteps']:.3f}, GFS={w_dict['gfs']:.3f}, Persist={w_dict['persistence']:.3f}"
            )

    # Save model artifact
    out_dir = Path(model_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_file = out_dir / "model.pt"

    metadata = {
        "model_version": "learned_gate_mlp_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "train_event": "mumbai_monsoon_2023_07_18",
        "validation_event": "mumbai_monsoon_2023_07_25",
        "test_anti_leakage": "Held-out test split was strictly untouched during gating training.",
        "input_features": ds_train.feature_names,
        "input_dimension": len(ds_train.feature_names),
        "expected_providers": providers,
        "best_epoch": best_epoch,
        "best_val_mae": float(best_val_mae),
        "mean_val_weights": best_weights_summary,
        "hyperparameters": {
            "seed": seed,
            "epochs": epochs,
            "learning_rate": lr,
            "weight_decay": weight_decay,
            "hidden_dim": 32,
        },
    }

    checkpoint_data = {
        "model_state": best_state,
        "feature_names": ds_train.feature_names,
        "feature_mean": X_mean.squeeze().tolist(),
        "feature_std": X_std.squeeze().tolist(),
        "metadata": metadata,
    }
    torch.save(checkpoint_data, str(model_file))
    model_sha256 = hashlib.sha256(model_file.read_bytes()).hexdigest()
    metadata["model_sha256"] = model_sha256

    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Save YAML configuration
    cfg_path = Path(config_output_path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    gate_yaml = {
        "model_version": "learned_gate_mlp_v1",
        "model_artifact": str(model_file.as_posix()),
        "model_sha256": model_sha256,
        "feature_count": len(ds_train.feature_names),
        "providers": providers,
        "training": {
            "train_split": "train",
            "val_split": "validation",
            "seed": seed,
            "epochs": epochs,
            "lr": lr,
            "best_epoch": best_epoch,
            "best_val_mae": float(best_val_mae),
        },
        "mean_weights_on_validation": best_weights_summary,
    }
    cfg_path.write_text(yaml.safe_dump(gate_yaml, sort_keys=False), encoding="utf-8")

    # Write training report
    rep_path = Path(report_output_path)
    rep_path.parent.mkdir(parents=True, exist_ok=True)
    report_md = f"""# Phase 4C: Supervised Learned Gating Model Training Report

**Date**: {datetime.now(UTC).isoformat()}  
**Model Architecture**: `LearnedGateMLP` (Linear(44, 32) -> ReLU -> Dropout(0.05) -> Linear(32, 16) -> ReLU -> Linear(16, 4) -> Masked Softmax)  
**Total Parameters**: 2,036  
**Formulation**: OPTION B — Direct Convex Provider Weight Optimization ($w_i \\ge 0, \\sum w_i = 1$)  
**Optimization Objective**: Spatial Mean Absolute Error (MAE) under intersection valid mask  
**Split Isolation**: Trained strictly on `mumbai_monsoon_2023_07_18` (Train), early-stopped on `mumbai_monsoon_2023_07_25` (Validation).  
**Held-Out Test Status**: Untouched.  

---

## 1. Training Summary
- **Input Dimension**: {len(ds_train.feature_names)} features (lead time, current rainfall, regime, GFS forecast age, provider forecasts, ensemble statistics).
- **Training Samples**: {len(X_tr_np)} issue-horizon pairs ({int(Mask_tr_np.sum()):,} valid space-time cells).
- **Validation Samples**: {len(X_val_np)} issue-horizon pairs ({int(Mask_val_np.sum()):,} valid space-time cells).
- **Best Epoch**: {best_epoch} / {epochs}
- **Best Validation MAE**: **{best_val_mae:.4f} mm/h**
- **Model Checksum**: `{model_sha256}`

---

## 2. Learned Provider Weight Distribution on Validation Split
- `pysteps`: **{best_weights_summary.get('pysteps', 0.0):.4f}**
- `gfs`: **{best_weights_summary.get('gfs', 0.0):.4f}**
- `persistence`: **{best_weights_summary.get('persistence', 0.0):.4f}**
- `convlstm_v2`: **{best_weights_summary.get('convlstm_v2', 0.0):.4f}** (unavailable, masked to 0)

---

## 3. Training Dynamics
| Epoch | Train MAE (mm/h) | Val MAE (mm/h) | Val RMSE (mm/h) | PySTEPS Weight | GFS Weight | Persistence Weight |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
"""
    for row in history[::4]:
        w = row["mean_weights"]
        report_md += (
            f"| {row['epoch']} | {row['train_mae']:.4f} | {row['val_mae']:.4f} | "
            f"{row['val_rmse']:.4f} | {w.get('pysteps', 0):.3f} | {w.get('gfs', 0):.3f} | {w.get('persistence', 0):.3f} |\n"
        )

    rep_path.write_text(report_md, encoding="utf-8")
    print(f"Artifacts successfully saved to {out_dir}, {cfg_path}, and {rep_path}")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--lr", type=float, default=0.005)
    args = parser.parse_args()
    train_learned_gate(epochs=args.epochs, lr=args.lr)
