"""ConvLSTM V3 Nowcaster with Multi-Source Encoder, Spatial Feature Extractor, and Lead-Specific Heads."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import torch
from torch import nn

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMCell
from jalrakshak_ml.deep_nowcast.residual_convlstm import reconstruct_persistence_residual


class MultiSourceEncoder(nn.Module):
    """Encodes multi-source meteorological channels with missing-channel gating."""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1)
        self.norm1 = nn.BatchNorm2d(out_channels)
        self.act1 = nn.GELU()
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
        self.norm2 = nn.BatchNorm2d(out_channels)
        self.act2 = nn.GELU()

    def forward(
        self,
        x: torch.Tensor,
        missing_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Parameters:

        x: [B, C, H, W]
        missing_mask: [B, C] or None
        """
        if missing_mask is not None:
            # Mask out missing channels: [B, C, 1, 1]
            gate = (~missing_mask).to(dtype=x.dtype).unsqueeze(-1).unsqueeze(-1)
            x = x * gate
        h = self.act1(self.norm1(self.conv1(x)))
        return self.act2(self.norm2(self.conv2(h))) + h


class MultiScaleSpatialBlock(nn.Module):
    """Parallel multi-scale feature extractor (3x3 and 5x5 receptive fields)."""

    def __init__(self, channels: int):
        super().__init__()
        mid = channels // 2
        self.branch3 = nn.Sequential(
            nn.Conv2d(channels, mid, kernel_size=3, padding=1),
            nn.BatchNorm2d(mid),
            nn.GELU(),
        )
        self.branch5 = nn.Sequential(
            nn.Conv2d(channels, mid, kernel_size=5, padding=2),
            nn.BatchNorm2d(mid),
            nn.GELU(),
        )
        self.proj = nn.Sequential(
            nn.Conv2d(mid * 2, channels, kernel_size=1),
            nn.BatchNorm2d(channels),
            nn.GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b3 = self.branch3(x)
        b5 = self.branch5(x)
        cat = torch.cat([b3, b5], dim=1)
        return x + self.proj(cat)


class LeadSpecificHead(nn.Module):
    """Horizon-specific decoder head outputting physical delta rainfall."""

    def __init__(self, in_channels: int, head_channels: int = 16, horizon_idx: int = 0):
        super().__init__()
        self.horizon_idx = horizon_idx
        # Lead embedding representation
        self.lead_conv = nn.Sequential(
            nn.Conv2d(in_channels, head_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(head_channels),
            nn.GELU(),
            nn.Conv2d(head_channels, 1, kernel_size=1),
        )
        # Initialize zero weights for stable residual start
        nn.init.zeros_(self.lead_conv[-1].weight)
        nn.init.zeros_(self.lead_conv[-1].bias)

    def forward(self, feat: torch.Tensor) -> torch.Tensor:
        return self.lead_conv(feat)


class ConvLSTMNowcasterV3(nn.Module):
    """ConvLSTM V3: Multi-source encoder, multi-scale spatial core, ConvLSTM, and lead-specific heads."""

    model_version = "convlstm_v3"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        hidden_channels: int | Sequence[int] = (24, 24),
        output_horizons: int = 4,
        kernel_size: int = 3,
        head_channels: int = 16,
    ):
        super().__init__()
        if isinstance(hidden_channels, int):
            hidden = [hidden_channels, hidden_channels]
        else:
            hidden = [int(h) for h in hidden_channels]
        self.input_channels = input_channels
        self.hidden_channels = hidden
        self.output_horizons = output_horizons
        self.head_channels = head_channels

        # 1. Multi-source encoder
        base_features = hidden[0]
        self.encoder = MultiSourceEncoder(input_channels, base_features)
        self.spatial_block = MultiScaleSpatialBlock(base_features)

        # 2. ConvLSTM temporal core
        cells = []
        prev = base_features
        for ch in hidden:
            cells.append(ConvLSTMCell(prev, ch, kernel_size=kernel_size))
            prev = ch
        self.cells = nn.ModuleList(cells)

        # 3. 4 Lead-specific heads
        self.lead_heads = nn.ModuleList([
            LeadSpecificHead(hidden[-1], head_channels=head_channels, horizon_idx=i)
            for i in range(output_horizons)
        ])

    def config_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "forecast_mode": self.forecast_mode,
            "input_channels": self.input_channels,
            "hidden_channels": list(self.hidden_channels),
            "output_horizons": self.output_horizons,
            "head_channels": self.head_channels,
        }

    def predict_residual(
        self,
        inputs: torch.Tensor,
        missing_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Predict horizon-specific signed rainfall residuals.

        Parameters:
        inputs: [B, T, C, H, W]
        missing_mask: [B, C] or None
        """
        b, t, c, h, w = inputs.shape
        states = [
            (
                inputs.new_zeros((b, hid, h, w)),
                inputs.new_zeros((b, hid, h, w)),
            )
            for hid in self.hidden_channels
        ]

        for step in range(t):
            step_in = inputs[:, step]  # [B, C, H, W]
            feat = self.encoder(step_in, missing_mask=missing_mask)
            feat = self.spatial_block(feat)

            layer_input = feat
            for l_idx, cell in enumerate(self.cells):
                states[l_idx] = cell(layer_input, states[l_idx])
                layer_input = states[l_idx][0]

        last_hidden = states[-1][0]  # [B, hidden[-1], H, W]

        # Apply each lead-specific head
        lead_outputs = []
        for head in self.lead_heads:
            delta = head(last_hidden)  # [B, 1, H, W]
            lead_outputs.append(delta)

        # Stack into [B, output_horizons, 1, H, W]
        return torch.stack(lead_outputs, dim=1)

    def forward(
        self,
        inputs: torch.Tensor,
        persistence_baseline: torch.Tensor,
        missing_channel_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Returns non-negative rainfall forecast [B, output_horizons, 1, H, W]."""
        residual = self.predict_residual(inputs, missing_mask=missing_channel_mask)
        return reconstruct_persistence_residual(persistence_baseline, residual)
