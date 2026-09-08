"""Persistence-residual ConvLSTM for heavy-rain-aware Phase-3 V2 training."""
from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMCell


def reconstruct_persistence_residual(
    persistence_baseline: torch.Tensor,
    residual: torch.Tensor,
) -> torch.Tensor:
    """Reconstruct non-negative physical rainfall from baseline plus residual."""
    if residual.ndim != 5:
        raise ValueError("residual must have shape [B,horizon,C,H,W]")
    baseline = persistence_baseline
    if baseline.ndim == 3:
        baseline = baseline[:, None]
    if baseline.ndim == 4:
        baseline = baseline[:, None]
    if baseline.ndim != 5:
        raise ValueError("persistence_baseline must have shape [B,C,H,W] or [B,1,C,H,W]")
    if baseline.shape[0] != residual.shape[0] or baseline.shape[-3:] != residual.shape[-3:]:
        raise ValueError("persistence baseline and residual batch/channel/grid dimensions differ")
    if baseline.shape[1] not in (1, residual.shape[1]):
        raise ValueError("persistence baseline must have one or exactly horizon time steps")
    return torch.clamp(baseline + residual, min=0.0)


class PersistenceResidualConvLSTMNowcaster(nn.Module):
    """Predict signed physical mm/h changes relative to the latest observation."""

    forecast_mode = "persistence_residual_physical"

    def __init__(
        self,
        *,
        input_channels: int = 1,
        hidden_channels: int | Sequence[int] = (16, 16),
        num_layers: int | None = None,
        output_horizons: int = 4,
        output_channels: int = 1,
        kernel_size: int = 3,
        head_channels: int = 16,
    ):
        super().__init__()
        if isinstance(hidden_channels, int):
            if num_layers is None:
                num_layers = 1
            hidden = [hidden_channels] * num_layers
        else:
            hidden = [int(value) for value in hidden_channels]
            if num_layers is not None and num_layers != len(hidden):
                raise ValueError("num_layers must match the hidden_channels list")
        if not hidden or any(value <= 0 for value in hidden):
            raise ValueError("hidden_channels must contain positive values")
        if input_channels < 1 or output_horizons < 1 or output_channels < 1:
            raise ValueError("input/output channel and horizon counts must be positive")

        self.input_channels = input_channels
        self.hidden_channels = hidden
        self.output_horizons = output_horizons
        self.output_channels = output_channels
        self.kernel_size = kernel_size
        self.head_channels = head_channels

        cells = []
        previous_channels = input_channels
        for channels in hidden:
            cells.append(ConvLSTMCell(previous_channels, channels, kernel_size))
            previous_channels = channels
        self.cells = nn.ModuleList(cells)
        final_layer = nn.Conv2d(
            head_channels,
            output_horizons * output_channels,
            kernel_size=1,
        )
        nn.init.zeros_(final_layer.weight)
        nn.init.zeros_(final_layer.bias)
        self.residual_head = nn.Sequential(
            nn.Conv2d(hidden[-1], head_channels, kernel_size=3, padding=1),
            nn.GELU(),
            final_layer,
        )

    def config_dict(self) -> dict:
        return {
            "forecast_mode": self.forecast_mode,
            "input_channels": self.input_channels,
            "hidden_channels": list(self.hidden_channels),
            "num_layers": len(self.hidden_channels),
            "output_horizons": self.output_horizons,
            "output_channels": self.output_channels,
            "kernel_size": self.kernel_size,
            "head_channels": self.head_channels,
        }

    def predict_residual(self, inputs: torch.Tensor) -> torch.Tensor:
        """Return signed residual rainfall in physical mm/h."""
        if inputs.ndim != 5:
            raise ValueError("ConvLSTM inputs must have shape [B,T,C,H,W]")
        batch, steps, channels, height, width = inputs.shape
        if steps < 1 or channels != self.input_channels:
            raise ValueError(
                f"Expected at least one step and {self.input_channels} channels; "
                f"got {tuple(inputs.shape)}"
            )
        states = [
            (
                inputs.new_zeros((batch, hidden, height, width)),
                inputs.new_zeros((batch, hidden, height, width)),
            )
            for hidden in self.hidden_channels
        ]
        for step in range(steps):
            layer_input = inputs[:, step]
            for layer, cell in enumerate(self.cells):
                states[layer] = cell(layer_input, states[layer])
                layer_input = states[layer][0]
        residual = self.residual_head(states[-1][0])
        return residual.view(
            batch,
            self.output_horizons,
            self.output_channels,
            height,
            width,
        )

    def forward(
        self,
        inputs: torch.Tensor,
        persistence_baseline: torch.Tensor,
    ) -> torch.Tensor:
        residual = self.predict_residual(inputs)
        return reconstruct_persistence_residual(persistence_baseline, residual)
