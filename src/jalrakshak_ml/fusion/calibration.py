"""Calibration of skill-derived fusion weights strictly using train and validation events.

Anti-leakage guarantee: Test events (2023-08-24, 2024-08-04, 2024-09-05) are NEVER used
to fit or calibrate weights.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml
import zarr

from jalrakshak_ml.deep_nowcast.dataset import RainfallSequenceDataset, build_datasets_from_config
from jalrakshak_ml.deep_nowcast.verification import pool_metric_rows
from jalrakshak_ml.evaluation.evaluator import NowcastEvaluator
from jalrakshak_ml.nowcast.persistence import PersistenceNowcast
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast


def calibrate_skill_weights(
    train_dataset: RainfallSequenceDataset,
    val_dataset: RainfallSequenceDataset,
    *,
    horizons_min: Sequence[int] = (30, 60, 90, 120),
    temporal_step_minutes: int = 30,
    output_weights_path: str | Path = "configs/fusion/weights_v1.yaml",
) -> dict[str, Any]:
    """Calibrate skill-derived weights using inverse MAE on validation split (post-train).

    Ensures zero leakage: asserts dataset.split is NOT 'test'.
    """
    if train_dataset.split != "train":
        raise ValueError(f"train_dataset split must be 'train', got {train_dataset.split!r}")
    if val_dataset.split != "validation":
        raise ValueError(f"val_dataset split must be 'validation', got {val_dataset.split!r}")

    evaluator = NowcastEvaluator(thresholds=[0.1, 1.0, 5.0])
    persistence = PersistenceNowcast()
    pysteps = PystepsNowcast()

    # We evaluate nowcasting models on validation split
    providers = {
        "persistence": persistence,
        "pysteps": pysteps,
    }

    rows: dict[str, list[list[dict[str, Any]]]] = {name: [] for name in providers}

    for idx in range(len(val_dataset)):
        raw = val_dataset.get_raw(idx)
        history = raw["inputs"]
        rain_hist = history[:, val_dataset.input_channels.index("rainfall")]
        obs = raw["target"][:, 0]
        vmask = raw["target_mask"][:, 0].astype(bool) & np.isfinite(obs)
        leads = obs.shape[0]

        preds = {
            "persistence": persistence.predict(rain_hist[-1], leads),
            "pysteps": pysteps.predict(rain_hist, leads),
        }

        common_mask = vmask.copy()
        for p in preds.values():
            common_mask &= np.isfinite(p)

        for name, p in preds.items():
            df = evaluator.evaluate_sequence(obs, p, valid_mask=common_mask)
            rows[name].append(df.to_dict(orient="records"))

    metrics: dict[str, Any] = {}
    for name, sample_rows in rows.items():
        metrics[name] = pool_metric_rows(sample_rows, thresholds=[0.1, 1.0, 5.0])

    # Compute inverse MAE weights per horizon
    # For GFS: Since GFS was not replayed for 2023-07-25 validation window,
    # we use a documented prior regularizer (NWP climatological weight growing with lead time)
    # or calibrate purely between available nowcasters, with GFS prior.
    calibrated_weights: dict[int, dict[str, float]] = {}
    lead_count = len(horizons_min)

    for lead_idx in range(lead_count):
        h_min = horizons_min[lead_idx]
        pysteps_mae = metrics["pysteps"]["by_lead"][lead_idx]["mae"] or 1.0
        persist_mae = metrics["persistence"]["by_lead"][lead_idx]["mae"] or 1.0

        inv_pysteps = 1.0 / max(0.01, pysteps_mae)
        inv_persist = 1.0 / max(0.01, persist_mae)

        # Baseline skill allocation between PySTEPS and Persistence:
        total_nowcast = inv_pysteps + inv_persist
        w_pysteps = inv_pysteps / total_nowcast
        w_persist = inv_persist / total_nowcast

        # Physical horizon transition: optical flow decays by lead 4; NWP guidance transitions in.
        # At +30m: 85% nowcaster skill, 15% NWP
        # At +60m: 70% nowcaster skill, 30% NWP
        # At +90m: 50% nowcaster skill, 50% NWP
        # At +120m: 30% nowcaster skill, 70% NWP
        nwp_prior_share = [0.15, 0.30, 0.50, 0.70][lead_idx]
        nowcast_share = 1.0 - nwp_prior_share

        calibrated_weights[h_min] = {
            "pysteps": float(round(w_pysteps * nowcast_share, 4)),
            "persistence": float(round(w_persist * nowcast_share, 4)),
            "gfs": float(round(nwp_prior_share, 4)),
            "convlstm_v2": 0.0,  # Unvalidated model receives 0 weight in operational skill baseline
        }
        # Re-normalize to exactly 1.0
        tot = sum(calibrated_weights[h_min].values())
        calibrated_weights[h_min] = {
            k: float(round(v / tot, 4)) for k, v in calibrated_weights[h_min].items()
        }

    manifest = {
        "calibration_version": "fusion_weights_v1",
        "calibration_timestamp": datetime.now(UTC).isoformat(),
        "calibration_splits": ["train", "validation"],
        "calibration_events": {
            "train": list(train_dataset.event_ids),
            "validation": list(val_dataset.event_ids),
        },
        "anti_leakage_guarantee": "Strictly zero test event access during weight calibration.",
        "objective": "inverse_mae_validation_skill_with_nwp_lead_transition",
        "validation_metrics": {
            name: {
                "mae_by_lead": [row["mae"] for row in m["by_lead"]],
                "rmse_by_lead": [row["rmse"] for row in m["by_lead"]],
            }
            for name, m in metrics.items()
        },
        "weights_by_horizon": calibrated_weights,
    }

    out_path = Path(output_weights_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    return manifest
