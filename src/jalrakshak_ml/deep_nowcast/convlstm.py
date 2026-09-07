"""Compact deterministic ConvLSTM rainfall nowcaster."""
from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn
from torch.nn import functional as F


class ConvLSTMCell(nn.Module):
    def __init__(self, input_channels: int, hidden_channels: int, kernel_size: int = 3):
        super().__init__()
        if kernel_size % 2 == 0:
            raise ValueError("kernel_size must be odd so spatial dimensions are preserved")
        self.input_channels = input_channels
        self.hidden_channels = hidden_channels
        self.gates = nn.Conv2d(
            input_channels + hidden_channels,
            4 * hidden_channels,
            kernel_size=kernel_size,
            padding=kernel_size // 2,
        )

    def forward(
        self,
        inputs: torch.Tensor,
        state: tuple[torch.Tensor, torch.Tensor],
    ) -> tuple[torch.Tensor, torch.Tensor]:
        hidden, cell = state
        input_gate, forget_gate, output_gate, candidate = self.gates(
            torch.cat([inputs, hidden], dim=1)
        ).chunk(4, dim=1)
        input_gate = torch.sigmoid(input_gate)
        forget_gate = torch.sigmoid(forget_gate)
        output_gate = torch.sigmoid(output_gate)
        candidate = torch.tanh(candidate)
        next_cell = forget_gate * cell + input_gate * candidate
        next_hidden = output_gate * torch.tanh(next_cell)
        return next_hidden, next_cell


class ConvLSTMNowcaster(nn.Module):
    """Encode rainfall history and emit all deterministic horizons at once.

    Inputs use ``[batch, time, channels, height, width]``. Outputs use
    ``[batch, horizon, output_channels, height, width]`` and are non-negative
    in normalized log-rainfall space. The prediction head is deliberately
    isolated so probabilistic/quantile heads can replace it later.
    """

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
        self.prediction_head = nn.Sequential(
            nn.Conv2d(hidden[-1], head_channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv2d(head_channels, output_horizons * output_channels, kernel_size=1),
        )

    def config_dict(self) -> dict:
        return {
            "input_channels": self.input_channels,
            "hidden_channels": list(self.hidden_channels),
            "num_layers": len(self.hidden_channels),
            "output_horizons": self.output_horizons,
            "output_channels": self.output_channels,
            "kernel_size": self.kernel_size,
            "head_channels": self.head_channels,
        }

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        if inputs.ndim != 5:
            raise ValueError("ConvLSTM inputs must have shape [B,T,C,H,W]")
        batch, steps, channels, height, width = inputs.shape
        if steps < 1 or channels != self.input_channels:
            raise ValueError(
                f"Expected at least one step and {self.input_channels} channels; got {tuple(inputs.shape)}"
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
        raw = self.prediction_head(states[-1][0])
        non_negative = F.softplus(raw)
        return non_negative.view(
            batch,
            self.output_horizons,
            self.output_channels,
            height,
            width,
        )
