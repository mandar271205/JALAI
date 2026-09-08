"""U-Net Spatial Encoder-Decoder with ConvGRU Temporal Bottleneck."""
from __future__ import annotations

from typing import Any

import torch
from torch import nn

from jalrakshak_ml.deep_nowcast.residual_convlstm import reconstruct_persistence_residual


class ConvGRUCell(nn.Module):
    """Convolutional Gated Recurrent Unit (ConvGRU) Cell."""

    def __init__(self, in_channels: int, hidden_channels: int, kernel_size: int = 3):
        super().__init__()
        self.in_channels = in_channels
        self.hidden_channels = hidden_channels
        padding = kernel_size // 2

        # Reset and update gates combined
        self.conv_gates = nn.Conv2d(
            in_channels + hidden_channels,
            2 * hidden_channels,
            kernel_size=kernel_size,
            padding=padding,
        )
        # Candidate hidden state
        self.conv_candidate = nn.Conv2d(
            in_channels + hidden_channels,
            hidden_channels,
            kernel_size=kernel_size,
            padding=padding,
        )

    def forward(self, x: torch.Tensor, h_prev: torch.Tensor) -> torch.Tensor:
        combined = torch.cat([x, h_prev], dim=1)
        gates = torch.sigmoid(self.conv_gates(combined))
        r, z = torch.chunk(gates, 2, dim=1)
        combined_candidate = torch.cat([x, r * h_prev], dim=1)
        h_cand = torch.tanh(self.conv_candidate(combined_candidate))
        h_next = (1.0 - z) * h_prev + z * h_cand
        return h_next


class DoubleConv(nn.Module):
    """(Conv2D -> BatchNorm -> GELU) * 2."""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.GELU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class UNetConvGRUNowcaster(nn.Module):
    """U-Net spatial encoder/decoder with ConvGRU bottleneck and lead-specific heads."""

    model_version = "unet_convgru_v1"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        base_channels: int = 16,
        bottleneck_channels: int = 48,
        output_horizons: int = 4,
        head_channels: int = 16,
    ):
        super().__init__()
        self.input_channels = input_channels
        self.base_channels = base_channels
        self.bottleneck_channels = bottleneck_channels
        self.output_horizons = output_horizons
        self.head_channels = head_channels

        # Encoder stages:
        # Input (128x128) -> enc1 (base_channels, 128x128)
        self.enc1 = DoubleConv(input_channels, base_channels)
        self.down1 = nn.MaxPool2d(2)  # 64x64

        # Down1 -> enc2 (2*base_channels, 64x64)
        self.enc2 = DoubleConv(base_channels, base_channels * 2)
        self.down2 = nn.MaxPool2d(2)  # 32x32

        # Bottleneck pre-conv (32x32)
        self.pre_bottleneck = DoubleConv(base_channels * 2, bottleneck_channels)

        # ConvGRU at bottleneck resolution (32x32)
        self.convgru = ConvGRUCell(bottleneck_channels, bottleneck_channels, kernel_size=3)

        # Decoder stages:
        # Up1 (32x32 -> 64x64) + skip from enc2 (2*base_channels)
        self.up1 = nn.ConvTranspose2d(bottleneck_channels, base_channels * 2, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(base_channels * 4, base_channels * 2)

        # Up2 (64x64 -> 128x128) + skip from enc1 (base_channels)
        self.up2 = nn.ConvTranspose2d(base_channels * 2, base_channels, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(base_channels * 2, base_channels)

        # 4 Lead-specific heads at native 128x128
        self.lead_heads = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(base_channels, head_channels, kernel_size=3, padding=1),
                nn.BatchNorm2d(head_channels),
                nn.GELU(),
                nn.Conv2d(head_channels, 1, kernel_size=1),
            )
            for _ in range(output_horizons)
        ])
        for head in self.lead_heads:
            nn.init.zeros_(head[-1].weight)
            nn.init.zeros_(head[-1].bias)

    def config_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "forecast_mode": self.forecast_mode,
            "input_channels": self.input_channels,
            "base_channels": self.base_channels,
            "bottleneck_channels": self.bottleneck_channels,
            "output_horizons": self.output_horizons,
            "head_channels": self.head_channels,
        }

    def predict_residual(
        self,
        inputs: torch.Tensor,
        missing_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Inputs: [B, T, C, H, W]

        missing_mask: [B, C] or None
        """
        b, t, c, h, w = inputs.shape
        if missing_mask is not None:
            gate = (~missing_mask).to(dtype=inputs.dtype).view(b, 1, c, 1, 1)
            inputs = inputs * gate

        # Temporal bottleneck recurrent state
        h_bottleneck = inputs.new_zeros((b, self.bottleneck_channels, h // 4, w // 4))

        # We will save the encoder skip connections from the latest timestep (t-1)
        latest_skip1: torch.Tensor | None = None
        latest_skip2: torch.Tensor | None = None

        for step in range(t):
            step_in = inputs[:, step]  # [B, C, H, W]
            s1 = self.enc1(step_in)    # [B, base_ch, 128, 128]
            d1 = self.down1(s1)        # [B, base_ch, 64, 64]
            s2 = self.enc2(d1)         # [B, 2*base_ch, 64, 64]
            d2 = self.down2(s2)        # [B, 2*base_ch, 32, 32]
            bottle_in = self.pre_bottleneck(d2)

            h_bottleneck = self.convgru(bottle_in, h_bottleneck)
            if step == t - 1:
                latest_skip1 = s1
                latest_skip2 = s2

        # Decoder starting from recurrent bottleneck
        u1 = self.up1(h_bottleneck)                         # [B, 2*base_ch, 64, 64]
        cat1 = torch.cat([u1, latest_skip2], dim=1)         # [B, 4*base_ch, 64, 64]
        feat1 = self.dec1(cat1)                             # [B, 2*base_ch, 64, 64]

        u2 = self.up2(feat1)                                # [B, base_ch, 128, 128]
        cat2 = torch.cat([u2, latest_skip1], dim=1)         # [B, 2*base_ch, 128, 128]
        feat_final = self.dec2(cat2)                        # [B, base_ch, 128, 128]

        # 4 Lead-specific heads
        lead_outputs = []
        for head in self.lead_heads:
            delta = head(feat_final)                        # [B, 1, 128, 128]
            lead_outputs.append(delta)

        return torch.stack(lead_outputs, dim=1)

    def forward(
        self,
        inputs: torch.Tensor,
        persistence_baseline: torch.Tensor,
        missing_channel_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        residual = self.predict_residual(inputs, missing_mask=missing_channel_mask)
        return reconstruct_persistence_residual(persistence_baseline, residual)
