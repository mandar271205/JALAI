"""Scientifically simple deterministic rainfall loss."""
from __future__ import annotations

from itertools import pairwise

import torch
from torch import nn
from torch.nn import functional as F


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


class MultiScalePiecewiseLoss(nn.Module):
    """Multi-scale physical heavy-rain-aware loss evaluating native and pooled scales.

    Combines intensity-weighted MAE + MSE at native grid (e.g. 128x128)
    and coarse pooled representation (e.g. 64x64) to penalize both fine-scale
    displacement and broader rain-structure errors.
    """

    def __init__(
        self,
        *,
        thresholds_mm_h: list[float] | tuple[float, ...] = (1.0, 5.0, 10.0),
        weights: list[float] | tuple[float, ...] = (1.0, 2.0, 6.0, 10.0),
        mse_weight: float = 0.05,
        coarse_scale_weight: float = 0.25,
        pool_kernel: int = 2,
    ):
        super().__init__()
        self.base_loss = HeavyRainAwareLoss(
            thresholds_mm_h=thresholds_mm_h,
            weights=weights,
            mse_weight=mse_weight,
        )
        self.coarse_scale_weight = float(coarse_scale_weight)
        self.pool_kernel = int(pool_kernel)
        if self.pool_kernel <= 0:
            raise ValueError("pool_kernel must be positive")

    def masked_pool(
        self,
        prediction_physical: torch.Tensor,
        target_physical: torch.Tensor,
        target_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Aggregate prediction and target over the same valid-pixel support.

        Returns pooled prediction, pooled target, the coarse validity mask, and
        valid-pixel counts. Blocks with partial coverage use valid-only means;
        blocks with no valid target pixels carry no supervision. Predictions are
        aggregated over exactly the same target-valid support.
        """
        if prediction_physical.shape != target_physical.shape:
            raise ValueError(
                f"Shape mismatch: {prediction_physical.shape} != {target_physical.shape}"
            )
        if target_mask.shape != target_physical.shape:
            raise ValueError("target_mask must match target_physical shape")
        if prediction_physical.ndim != 5:
            raise ValueError("Multi-scale tensors must have shape [B, T, C, H, W]")
        b, t, c, h, w = prediction_physical.shape
        if h % self.pool_kernel or w % self.pool_kernel:
            raise ValueError("Spatial dimensions must be divisible by pool_kernel")

        pred_flat = prediction_physical.reshape(b * t, c, h, w)
        tgt_flat = target_physical.reshape(b * t, c, h, w)
        mask_flat = target_mask.reshape(b * t, c, h, w).to(dtype=torch.bool)
        supervision_valid = mask_flat & torch.isfinite(tgt_flat)
        support_values = supervision_valid.to(dtype=pred_flat.dtype)
        area = float(self.pool_kernel * self.pool_kernel)
        support = F.avg_pool2d(
            support_values,
            kernel_size=self.pool_kernel,
            stride=self.pool_kernel,
        ) * area
        pred_sum = F.avg_pool2d(
            torch.where(supervision_valid, pred_flat, torch.zeros_like(pred_flat)),
            kernel_size=self.pool_kernel,
            stride=self.pool_kernel,
        ) * area
        target_sum = F.avg_pool2d(
            torch.where(supervision_valid, tgt_flat, torch.zeros_like(tgt_flat)),
            kernel_size=self.pool_kernel,
            stride=self.pool_kernel,
        ) * area
        denominator = support.clamp_min(1.0)
        coarse_shape = (b, t, c, h // self.pool_kernel, w // self.pool_kernel)
        return (
            (pred_sum / denominator).reshape(coarse_shape),
            (target_sum / denominator).reshape(coarse_shape),
            (support > 0).reshape(coarse_shape),
            support.reshape(coarse_shape),
        )

    def forward(
        self,
        prediction_physical: torch.Tensor,
        target_physical: torch.Tensor,
        target_mask: torch.Tensor,
    ) -> torch.Tensor:
        native_loss = self.base_loss(prediction_physical, target_physical, target_mask)
        if self.coarse_scale_weight <= 0.0:
            return native_loss

        pred_coarse, tgt_coarse, mask_coarse, _ = self.masked_pool(
            prediction_physical, target_physical, target_mask
        )

        coarse_loss = self.base_loss(pred_coarse, tgt_coarse, mask_coarse)
        return native_loss + self.coarse_scale_weight * coarse_loss

    def compute_components(
        self,
        prediction_physical: torch.Tensor,
        target_physical: torch.Tensor,
        target_mask: torch.Tensor,
    ) -> dict[str, float]:
        with torch.no_grad():
            native_loss = self.base_loss(prediction_physical, target_physical, target_mask)
            pred_coarse, tgt_coarse, mask_coarse, _ = self.masked_pool(
                prediction_physical, target_physical, target_mask
            )

            coarse_loss = self.base_loss(pred_coarse, tgt_coarse, mask_coarse)
            total = native_loss + self.coarse_scale_weight * coarse_loss
            return {
                "native_loss": float(native_loss.item()),
                "coarse_loss": float(coarse_loss.item()),
                "total_loss": float(total.item()),
            }


