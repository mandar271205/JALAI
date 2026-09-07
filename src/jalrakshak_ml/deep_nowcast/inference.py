"""CPU/GPU inference adapter for trained ConvLSTM checkpoints."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer
from jalrakshak_ml.deep_nowcast.train import resolve_device
from jalrakshak_ml.nowcast.contracts import NowcastResult, build_result
from jalrakshak_ml.utils.hashing import sha256_file


class ConvLSTMInference:
    """Provider-compatible inference wrapper that accepts raw mm/h histories."""

    def __init__(self, checkpoint_path: str | Path, device: str = "auto"):
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self.device = resolve_device(device)
        checkpoint = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)
        self.model = ConvLSTMNowcaster(**checkpoint["model_config"])
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device).eval()
        self.normalizer = LogRainNormalizer.from_dict(checkpoint["normalizer"])
        self.model_version = str(checkpoint["model_version"])
        self.data_version = str(checkpoint["data_version"])
        self.checkpoint_hash = sha256_file(self.checkpoint_path)
        self.training_metadata = {
            "training_epoch": int(checkpoint["epoch"]),
            "best_validation_loss": float(checkpoint["best_validation_loss"]),
            "forecast_type": checkpoint.get("forecast_type", "deterministic"),
        }

    def predict(self, recent_states: np.ndarray, lead_times: int | None = None) -> np.ndarray:
        """Predict raw rainfall with output shape ``[horizon, H, W]``."""
        recent = np.asarray(recent_states, dtype=np.float32)
        if recent.ndim == 3:
            recent = recent[:, None]
        if recent.ndim != 4:
            raise ValueError("recent_states must have shape [T,H,W] or [T,C,H,W]")
        if recent.shape[1] != self.model.input_channels:
            raise ValueError(
                f"Checkpoint expects {self.model.input_channels} input channels; got {recent.shape[1]}"
            )
        requested = self.model.output_horizons if lead_times is None else int(lead_times)
        if requested < 1 or requested > self.model.output_horizons:
            raise ValueError(
                f"lead_times must be in [1, {self.model.output_horizons}] for this checkpoint"
            )
        valid = np.isfinite(recent)
        normalized = recent.copy()
        normalized[:, 0] = self.normalizer.transform(normalized[:, 0])
        normalized[~valid] = 0.0
        tensor = torch.from_numpy(normalized[None]).to(self.device)
        with torch.inference_mode():
            prediction = self.model(tensor)[0, :requested, 0]
            rainfall = self.normalizer.inverse(prediction).cpu().numpy().astype(np.float32)
        latest_valid = valid[-1, 0]
        rainfall[:, ~latest_valid] = np.nan
        return rainfall

    def predict_result(
        self,
        recent_states: np.ndarray,
        lead_times: int | None = None,
        *,
        issue_time: datetime,
        data_version: str | None = None,
        temporal_step_minutes: int = 30,
        source_metadata: dict[str, Any] | None = None,
    ) -> NowcastResult:
        rainfall = self.predict(recent_states, lead_times)
        return build_result(
            rainfall,
            issue_time=issue_time,
            provider="convlstm",
            model_version=self.model_version,
            data_version=data_version or self.data_version,
            temporal_step_minutes=temporal_step_minutes,
            source_metadata={**self.training_metadata, **(source_metadata or {})},
            checkpoint_hash=self.checkpoint_hash,
        )
