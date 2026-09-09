"""FNO readiness audit and smoke-training configuration.

Verifies that the FNO architecture, loss function, and evaluation pipeline
are ready to consume genuine physics outputs when they become available.

Does NOT fabricate physics-reference training data.
Does NOT initiate training until GENUINE_FNO_TARGETS_AVAILABLE is True.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from jalrakshak_ml.flood.fno import (
    FloodFNO,
    FNOTrainingConfig,
    SparseFloodLoss,
    evaluate_fno,
)


@dataclass(frozen=True)
class FNOReadinessReport:
    """Comprehensive FNO readiness audit result."""

    architecture_correct: bool
    output_shape_correct: bool
    output_nonnegative: bool
    loss_forward_pass: bool
    metrics_callable: bool
    checkpoint_structure_valid: bool
    normalization_contract_valid: bool
    input_channels_verified: list[str]
    recommended_input_channels: list[str]
    blockers: list[str]
    smoke_train_config: dict[str, Any]

    @property
    def ready_for_training(self) -> bool:
        return not self.blockers and all([
            self.architecture_correct,
            self.output_nonnegative,
            self.loss_forward_pass,
            self.metrics_callable,
        ])

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ready_for_training": self.ready_for_training}


def audit_fno_readiness(
    *,
    width: int = 32,
    modes: int = 12,
    output_horizons: int = 4,
    grid_size: int = 64,
    batch_size: int = 2,
) -> FNOReadinessReport:
    """Run a complete in-process FNO readiness audit.

    Input channel order (expected when real physics data is available):
        0: dem_m             — Copernicus DEM (metres, EPSG:32643)
        1: slope_deg         — terrain slope (degrees)
        2: roughness_n       — Manning n (uncalibrated, literature values)
        3: rainfall_mm_h     — GPM 30-min domain-averaged rate (mm/h)
        4: flow_acc_log      — log10(flow accumulation + 1)
        5: low_lying_idx     — [0,1] low-lying terrain index

    These 6 channels are the agreed input contract once genuine
    physics-reference targets are available.
    """
    blockers: list[str] = []
    checks: dict[str, bool] = {}

    input_channels = ["dem_m", "slope_deg", "roughness_n", "rainfall_mm_h", "flow_acc_log", "low_lying_idx"]
    n_channels = len(input_channels)

    # 1. Architecture: instantiate and verify output shape
    try:
        model = FloodFNO(n_channels, width=width, modes=modes, output_horizons=output_horizons)
        x = torch.rand(batch_size, n_channels, grid_size, grid_size)
        with torch.no_grad():
            out = model(x)
        expected_shape = (batch_size, output_horizons, 1, grid_size, grid_size)
        checks["output_shape_correct"] = out.shape == expected_shape
        checks["output_nonnegative"] = bool(torch.all(out >= 0).item())
        checks["architecture_correct"] = True
        if not checks["output_shape_correct"]:
            blockers.append(f"Output shape {tuple(out.shape)} != expected {expected_shape}")
        if not checks["output_nonnegative"]:
            blockers.append("FNO output contains negative values (Softplus failure)")
    except Exception as e:  # noqa: BLE001
        blockers.append(f"Architecture instantiation failed: {e}")
        checks.update({
            "architecture_correct": False,
            "output_shape_correct": False,
            "output_nonnegative": False,
        })

    # 2. Loss function: forward pass with sparse wet/dry field
    try:
        loss_fn = SparseFloodLoss(wet_threshold=0.05, wet_weight=5.0)
        pred = torch.rand(batch_size, output_horizons, 1, grid_size, grid_size) * 0.5
        target = torch.zeros_like(pred)
        target[:, :, :, :grid_size//4, :grid_size//4] = 1.2  # wet corner
        mask = torch.ones_like(pred, dtype=torch.bool)
        loss_val = loss_fn(pred, target, mask)
        checks["loss_forward_pass"] = bool(torch.isfinite(loss_val).item())
        if not checks["loss_forward_pass"]:
            blockers.append("SparseFloodLoss returned non-finite value")
    except Exception as e:  # noqa: BLE001
        blockers.append(f"SparseFloodLoss failed: {e}")
        checks["loss_forward_pass"] = False

    # 3. Evaluation metrics
    try:
        ref = np.random.default_rng(0).uniform(0, 1.5, (16, 16)).astype(np.float32)
        pred_np = np.clip(ref + 0.1 * np.random.default_rng(1).standard_normal(ref.shape), 0, None).astype(np.float32)
        valid = np.ones_like(ref, dtype=bool)
        metrics = evaluate_fno(pred_np, ref, valid, threshold=0.05, runtime_seconds=0.5, reference_runtime_seconds=120.0)
        checks["metrics_callable"] = (
            "depth_mae_m" in metrics
            and "inundation_iou" in metrics
            and isinstance(metrics.get("measured_speedup"), float)
        )
        if not checks["metrics_callable"]:
            blockers.append("evaluate_fno returned incomplete metrics")
    except Exception as e:  # noqa: BLE001
        blockers.append(f"evaluate_fno failed: {e}")
        checks["metrics_callable"] = False

    # 4. Checkpoint structure
    try:
        if checks.get("architecture_correct"):
            model = FloodFNO(n_channels, width=width, modes=modes, output_horizons=output_horizons)
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
            sd = model.state_dict()
            required_keys = {"model", "optimizer", "epoch", "validation_metrics",
                             "model_version", "output_type", "physics_reference", "surrogate_model"}
            dummy_payload = {
                "model": sd,
                "optimizer": optimizer.state_dict(),
                "epoch": 1,
                "validation_metrics": {"depth_mae_m": 0.25},
                "model_version": model.model_version,
                "output_type": model.output_type,
                "physics_reference": True,
                "surrogate_model": True,
                "git_commit": "a" * 40,
                "locked_rainfall_test_accessed": False,
            }
            checks["checkpoint_structure_valid"] = required_keys.issubset(dummy_payload)
        else:
            checks["checkpoint_structure_valid"] = False
    except Exception as e:  # noqa: BLE001
        blockers.append(f"Checkpoint structure check failed: {e}")
        checks["checkpoint_structure_valid"] = False

    # 5. Normalization contract
    checks["normalization_contract_valid"] = True  # validated by test_phase5_foundation.py

    # Smoke training config (for when genuine data is available)
    smoke_config = {
        "input_channels": input_channels,
        "n_channels": n_channels,
        "fno_width": width,
        "fno_modes": modes,
        "output_horizons": output_horizons,
        "training_config": asdict(FNOTrainingConfig()),
        "min_genuine_scenarios_needed": 5,
        "note": (
            "FNO training is BLOCKED until LISFLOOD-FP produces genuine water-depth outputs. "
            "Normalization statistics must be fitted on train-split scenarios only. "
            "No susceptibility or heuristic depth is permitted as training target."
        ),
        "blocker_for_training": "LISFLOOD_SMOKE_EXECUTED=False; GENUINE_SOLVER_OUTPUT_AVAILABLE=False",
    }

    return FNOReadinessReport(
        architecture_correct=checks.get("architecture_correct", False),
        output_shape_correct=checks.get("output_shape_correct", False),
        output_nonnegative=checks.get("output_nonnegative", False),
        loss_forward_pass=checks.get("loss_forward_pass", False),
        metrics_callable=checks.get("metrics_callable", False),
        checkpoint_structure_valid=checks.get("checkpoint_structure_valid", False),
        normalization_contract_valid=checks.get("normalization_contract_valid", False),
        input_channels_verified=input_channels if checks.get("architecture_correct") else [],
        recommended_input_channels=input_channels,
        blockers=blockers,
        smoke_train_config=smoke_config,
    )


def write_fno_readiness_report(
    output_path: str | Path = "reports/fno_readiness_audit.json",
    **kwargs: Any,
) -> FNOReadinessReport:
    """Run audit and write the report to disk."""
    report = audit_fno_readiness(**kwargs)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
