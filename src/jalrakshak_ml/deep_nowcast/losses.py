"""Scientifically simple deterministic rainfall loss."""
from __future__ import annotations

import torch
from torch import nn


class WeightedRainfallLoss(nn.Module):
    """Masked L1 plus MSE with extra weight above a heavy-rain threshold.

    Values are expected in the non-negative normalized log-rainfall space.
    A valid-pixel mask prevents missing observations from contributing.
    """

    def __init__(
        self,
        *,
        heavy_threshold: float,
        heavy_weight: float = 3.0,
        mse_weight: float = 0.2,
    ):
        super().__init__()
        if heavy_threshold <= 0 or heavy_weight < 0 or mse_weight < 0:
            raise ValueError("Loss weights must be non-negative and threshold must be positive")
        self.heavy_threshold = heavy_threshold
        self.heavy_weight = heavy_weight
        self.mse_weight = mse_weight

    def forward(
        self,
        prediction: torch.Tensor,
        target: torch.Tensor,
        valid_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if prediction.shape != target.shape:
            raise ValueError(f"Shape mismatch: {prediction.shape} != {target.shape}")
        if valid_mask is None:
            valid_mask = torch.ones_like(target, dtype=torch.bool)
        if valid_mask.shape != target.shape:
            raise ValueError("valid_mask must match target shape")
        valid = valid_mask.to(dtype=target.dtype)
        denominator = valid.sum()
        if denominator.item() == 0:
            return prediction.sum() * 0.0
        event_strength = torch.clamp(target / self.heavy_threshold, min=0.0, max=1.0)
        weights = (1.0 + self.heavy_weight * event_strength) * valid
        error = prediction - target
        l1 = (weights * error.abs()).sum() / weights.sum().clamp_min(1.0)
        mse = (weights * error.square()).sum() / weights.sum().clamp_min(1.0)
        return l1 + self.mse_weight * mse
