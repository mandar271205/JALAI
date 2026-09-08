"""Scientifically simple deterministic rainfall loss."""
from __future__ import annotations

from itertools import pairwise

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


class HeavyRainAwareLoss(nn.Module):
    """Masked piecewise-weighted MAE plus MSE in physical rainfall units."""

    def __init__(
        self,
        *,
        thresholds_mm_h: list[float] | tuple[float, ...],
        weights: list[float] | tuple[float, ...],
        mse_weight: float = 0.05,
    ):
        super().__init__()
        thresholds = [float(value) for value in thresholds_mm_h]
        values = [float(value) for value in weights]
        if len(values) != len(thresholds) + 1:
            raise ValueError("weights must contain one more value than thresholds_mm_h")
        if any(value < 0 for value in thresholds) or any(
            right <= left for left, right in pairwise(thresholds)
        ):
            raise ValueError("thresholds_mm_h must be non-negative and strictly increasing")
        if any(value <= 0 for value in values) or mse_weight < 0:
            raise ValueError("intensity weights must be positive and mse_weight non-negative")
        self.thresholds_mm_h = tuple(thresholds)
        self.weights = tuple(values)
        self.mse_weight = float(mse_weight)

    def intensity_weights(self, target_physical: torch.Tensor) -> torch.Tensor:
        """Return configured weights using physical target rainfall boundaries."""
        output = torch.full_like(target_physical, self.weights[0])
        for threshold, weight in zip(
            self.thresholds_mm_h,
            self.weights[1:],
            strict=True,
        ):
            output = torch.where(target_physical >= threshold, weight, output)
        return output

    def forward(
        self,
        prediction_physical: torch.Tensor,
        target_physical: torch.Tensor,
        target_mask: torch.Tensor,
    ) -> torch.Tensor:
        if prediction_physical.shape != target_physical.shape:
            raise ValueError(
                f"Shape mismatch: {prediction_physical.shape} != {target_physical.shape}"
            )
        if target_mask.shape != target_physical.shape:
            raise ValueError("target_mask must match target_physical shape")
        valid = (
            target_mask.to(dtype=torch.bool)
            & torch.isfinite(target_physical)
            & torch.isfinite(prediction_physical)
        )
        if not torch.any(valid):
            return prediction_physical.sum() * 0.0
        intensity = self.intensity_weights(target_physical)
        pixel_weights = torch.where(valid, intensity, torch.zeros_like(intensity))
        error = torch.where(
            valid,
            prediction_physical - target_physical,
            torch.zeros_like(target_physical),
        )
        denominator = pixel_weights.sum().clamp_min(torch.finfo(pixel_weights.dtype).eps)
        mae = (pixel_weights * error.abs()).sum() / denominator
        mse = (pixel_weights * error.square()).sum() / denominator
        return mae + self.mse_weight * mse
