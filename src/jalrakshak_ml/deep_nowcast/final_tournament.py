"""Common-sample validation tournament orchestration without test access."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import torch

from .final_contracts import NWP_CHANNEL_ORDER
from .final_evaluation import evaluate_validation_events
from .splits import VALIDATION_EVENTS_AUTHORITATIVE, is_locked_test_event

Predictor = Callable[[dict[str, Any]], torch.Tensor | np.ndarray]
REQUIRED_MODELS = {
    "persistence",
    "pysteps",
    "convlstm_v3",
    "unet_convgru_v1",
    "st_attention_nowcaster_v1",
}


def persistence_predictor(batch: dict[str, Any]) -> torch.Tensor:
    baseline = batch["persistence_baseline"]
    if baseline.ndim != 4:
        raise ValueError("Persistence baseline must be [B,1,H,W]")
    return baseline[:, None].repeat(1, 4, 1, 1, 1)


def make_pysteps_predictor(model) -> Predictor:
    def predict(batch: dict[str, Any]) -> np.ndarray:
        histories = batch["obs_history_physical"].numpy()
        forecasts = []
        for history in histories:
            result = np.asarray(model.predict(history[:, 0], lead_times=4), dtype=np.float32)
            if result.shape != (4, *history.shape[-2:]):
                raise ValueError("PySTEPS output violates the four-horizon contract")
            forecasts.append(result[:, None])
        return np.stack(forecasts)

    return predict


def make_deep_predictor(model: torch.nn.Module, device: torch.device) -> Predictor:
    model.to(device).eval()

    def predict(batch: dict[str, Any]) -> torch.Tensor:
        with torch.no_grad():
            return model(
                obs_history=batch["obs_history"].to(device),
                nwp_future=batch["nwp_future"].to(device),
                static_features=batch["static_features"].to(device),
                persistence_baseline=batch["persistence_baseline"].to(device),
                missing_obs_mask=batch["missing_obs_mask"].to(device),
                missing_nwp_mask=batch["missing_nwp_mask"].to(device),
                missing_static_mask=batch["missing_static_mask"].to(device),
            )

    return predict


def run_common_validation_tournament(
    validation_loader,
    predictors: dict[str, Predictor],
    *,
    convlstm_v2_checkpoint_compatible: bool = False,
) -> dict[str, Any]:
    """Evaluate all predictors on the identical ordered validation samples and masks."""
    if getattr(validation_loader.dataset, "split", None) != "validation":
        raise PermissionError("Tournament accepts validation only")
    if tuple(getattr(validation_loader.dataset, "nwp_channel_order", ())) != NWP_CHANNEL_ORDER:
        raise ValueError("Tournament dataset has an incorrect or undocumented NWP channel order")
    indices = getattr(validation_loader.dataset, "indices", [])
    if any(is_locked_test_event(index.event_id) for index in indices):
        raise PermissionError("Locked test entered tournament")
    required = set(REQUIRED_MODELS)
    if convlstm_v2_checkpoint_compatible:
        required.add("convlstm_v2")
    if set(predictors) != required:
        raise ValueError(f"Tournament predictors must be exactly {sorted(required)}")

    collected: dict[str, dict[str, list[np.ndarray]]] = {model: {} for model in predictors}
    common_ids: list[str] = []
    for batch in validation_loader:
        metadata = batch["metadata"]
        event_ids = list(metadata["event_id"])
        issue_times = list(metadata["issue_time"])
        if len(event_ids) != batch["target_physical"].shape[0]:
            raise ValueError("Metadata/sample batch mismatch")
        common_ids.extend(
            f"{event}:{issue}" for event, issue in zip(event_ids, issue_times, strict=True)
        )
        target = batch["target_physical"].numpy()
        mask = batch["target_mask"].numpy()
        for model_name, predictor in predictors.items():
            predicted = predictor(batch)
            if isinstance(predicted, torch.Tensor):
                predicted = predicted.detach().cpu().numpy()
            if predicted.shape != target.shape:
                raise ValueError(f"{model_name} output shape differs from common target")
            for position, event_id in enumerate(event_ids):
                bucket = collected[model_name].setdefault(
                    event_id, {"prediction": [], "target": [], "mask": []}
                )
                bucket["prediction"].append(predicted[position : position + 1])
                bucket["target"].append(target[position : position + 1])
                bucket["mask"].append(mask[position : position + 1])

    if len(common_ids) != len(set(common_ids)):
        raise ValueError("Duplicate validation sample identity")
    if {event_id.split(":")[0] for event_id in common_ids} != set(VALIDATION_EVENTS_AUTHORITATIVE):
        raise ValueError("Tournament does not cover the exact validation events")
    reports = {}
    for model_name, by_event in collected.items():
        event_data = {
            event_id: tuple(
                np.concatenate(values[name]) for name in ("prediction", "target", "mask")
            )
            for event_id, values in by_event.items()
        }
        reports[model_name] = evaluate_validation_events(event_data)
    return {
        "models": reports,
        "common_sample_ids": common_ids,
        "common_sample_count": len(common_ids),
        "paired_common_samples": True,
        "identical_masks": True,
        "convlstm_v2_included": convlstm_v2_checkpoint_compatible,
        "locked_test_accessed": False,
    }
