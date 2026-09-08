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
    """U-Net spatial encoder/decoder with ConvGRU bottleneck, NWP horizon encoder, and lead-specific heads."""

    model_version = "unet_convgru_v1"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        obs_channels: int | None = None,
        nwp_channels: int | None = None,
        static_channels: int | None = None,
        base_channels: int = 16,
        bottleneck_channels: int = 48,
        output_horizons: int = 4,
        head_channels: int = 16,
        nwp_embed_dim: int = 8,
        static_embed_dim: int = 4,
    ):
        super().__init__()
        # Resolve channel counts
        if obs_channels is None:
            obs_channels = 1
        if nwp_channels is None:
            if input_channels == 1:
                nwp_channels = 0
            elif input_channels == 13:
                nwp_channels = 11
            else:
                nwp_channels = max(1, input_channels - 2)
        if static_channels is None:
            static_channels = 1 if input_channels >= 3 else 0

        self.input_channels = input_channels
        self.obs_channels = obs_channels
        self.nwp_channels = nwp_channels
        self.static_channels = static_channels
        self.base_channels = base_channels
        self.bottleneck_channels = bottleneck_channels
        self.output_horizons = output_horizons
        self.head_channels = head_channels
        self.nwp_embed_dim = nwp_embed_dim if nwp_channels > 0 else 0
        self.static_embed_dim = static_embed_dim if static_channels > 0 else 0

        # 1. Observation sequence encoder stages:
        # Input (128x128) -> enc1 (base_channels, 128x128)
        self.enc1 = DoubleConv(obs_channels, base_channels)
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

        # 2. NWP horizon encoder (encodes future NWP per horizon at native resolution)
        if self.nwp_channels > 0 and self.nwp_embed_dim > 0:
            self.nwp_encoder = nn.Sequential(
                nn.Conv2d(self.nwp_channels, self.nwp_embed_dim, kernel_size=3, padding=1),
                nn.BatchNorm2d(self.nwp_embed_dim),
                nn.GELU(),
            )
        else:
            self.nwp_encoder = None

        # 3. Static encoder (encodes DEM once)
        if self.static_channels > 0 and self.static_embed_dim > 0:
            self.static_encoder = nn.Sequential(
                nn.Conv2d(self.static_channels, self.static_embed_dim, kernel_size=3, padding=1),
                nn.BatchNorm2d(self.static_embed_dim),
                nn.GELU(),
            )
        else:
            self.static_encoder = None

        # 4. Lead-specific heads at native 128x128
        combined_dim = base_channels + self.nwp_embed_dim + self.static_embed_dim
        self.lead_heads = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(combined_dim, head_channels, kernel_size=3, padding=1),
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
            "obs_channels": self.obs_channels,
            "nwp_channels": self.nwp_channels,
            "static_channels": self.static_channels,
            "base_channels": self.base_channels,
            "bottleneck_channels": self.bottleneck_channels,
            "output_horizons": self.output_horizons,
            "head_channels": self.head_channels,
            "nwp_embed_dim": self.nwp_embed_dim,
            "static_embed_dim": self.static_embed_dim,
        }

    def _split_inputs(
        self, inputs: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
        b, t, c, h, w = inputs.shape
        if c == 1:
            obs = inputs
            nwp = None
            static = None
        elif c == 3:
            obs = inputs[:, :, 0:1]
            nwp = inputs[:, :, 1:2]
            static = inputs[:, 0, 2:3]
        elif c == 13:
            obs = inputs[:, :, 0:1]
            nwp = inputs[:, :, 1:12]
            static = inputs[:, 0, 12:13]
        else:
            obs = inputs[:, :, 0:self.obs_channels]
            if self.nwp_channels > 0 and c >= self.obs_channels + self.nwp_channels:
                nwp = inputs[:, :, self.obs_channels:self.obs_channels + self.nwp_channels]
            else:
                nwp = None
            if self.static_channels > 0 and c >= self.obs_channels + self.nwp_channels + self.static_channels:
                static = inputs[:, 0, -self.static_channels:]
            else:
                static = None
        return obs, nwp, static

    def predict_residual(
        self,
        inputs: torch.Tensor | None = None,
        missing_mask: torch.Tensor | None = None,
        *,
        obs_history: torch.Tensor | None = None,
        nwp_future: torch.Tensor | None = None,
        static_features: torch.Tensor | None = None,
        missing_obs_mask: torch.Tensor | None = None,
        missing_nwp_mask: torch.Tensor | None = None,
        missing_static_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if obs_history is None:
            if inputs is None:
                raise ValueError("Either obs_history or inputs must be provided.")
            obs_history, nwp_future, static_features = self._split_inputs(inputs)

        b, t_obs, _, h, w = obs_history.shape

        if missing_mask is not None and missing_obs_mask is None:
            if missing_mask.ndim == 1:
                missing_mask = missing_mask.unsqueeze(0).expand(b, -1)
            c_tot = missing_mask.shape[-1]
            if c_tot == 1:
                missing_obs_mask = missing_mask
            elif c_tot == 3:
                missing_obs_mask = missing_mask[:, 0:1]
                missing_nwp_mask = missing_mask[:, 1:2]
                missing_static_mask = missing_mask[:, 2:3]
            elif c_tot == 13:
                missing_obs_mask = missing_mask[:, 0:1]
                missing_nwp_mask = missing_mask[:, 1:12]
                missing_static_mask = missing_mask[:, 12:13]

        if missing_obs_mask is not None:
            o_gate = (~missing_obs_mask).to(dtype=obs_history.dtype).view(b, 1, -1, 1, 1)
            obs_history = obs_history * o_gate

        # Temporal bottleneck recurrent state over observation history
        h_bottleneck = obs_history.new_zeros((b, self.bottleneck_channels, h // 4, w // 4))

        latest_skip1: torch.Tensor | None = None
        latest_skip2: torch.Tensor | None = None

        for step in range(t_obs):
            step_in = obs_history[:, step]  # [B, C_obs, H, W]
            s1 = self.enc1(step_in)         # [B, base_ch, 128, 128]
            d1 = self.down1(s1)             # [B, base_ch, 64, 64]
            s2 = self.enc2(d1)              # [B, 2*base_ch, 64, 64]
            d2 = self.down2(s2)             # [B, 2*base_ch, 32, 32]
            bottle_in = self.pre_bottleneck(d2)

            h_bottleneck = self.convgru(bottle_in, h_bottleneck)
            if step == t_obs - 1:
                latest_skip1 = s1
                latest_skip2 = s2

        # Decoder starting from recurrent bottleneck
        u1 = self.up1(h_bottleneck)                         # [B, 2*base_ch, 64, 64]
        cat1 = torch.cat([u1, latest_skip2], dim=1)         # [B, 4*base_ch, 64, 64]
        feat1 = self.dec1(cat1)                             # [B, 2*base_ch, 64, 64]

        u2 = self.up2(feat1)                                # [B, base_ch, 128, 128]
        cat2 = torch.cat([u2, latest_skip1], dim=1)         # [B, 2*base_ch, 128, 128]
        feat_final = self.dec2(cat2)                        # [B, base_ch, 128, 128]

        # Static feature encoding
        if self.static_encoder is not None and static_features is not None:
            if missing_static_mask is not None:
                s_gate = (~missing_static_mask).to(dtype=static_features.dtype).view(b, -1, 1, 1)
                static_in = static_features * s_gate
            else:
                static_in = static_features
            static_feat = self.static_encoder(static_in)
        elif self.static_embed_dim > 0:
            static_feat = obs_history.new_zeros((b, self.static_embed_dim, h, w))
        else:
            static_feat = None

        # Lead-specific forecast heads combining decoded obs, horizon NWP, and static representations
        lead_outputs = []
        for h_idx in range(self.output_horizons):
            head_inputs = [feat_final]

            if self.nwp_encoder is not None and nwp_future is not None:
                horizon_nwp = nwp_future[:, h_idx]
                if missing_nwp_mask is not None:
                    n_gate = (~missing_nwp_mask).to(dtype=horizon_nwp.dtype).view(b, -1, 1, 1)
                    horizon_nwp = horizon_nwp * n_gate
                nwp_h_feat = self.nwp_encoder(horizon_nwp)
                head_inputs.append(nwp_h_feat)
            elif self.nwp_embed_dim > 0:
                head_inputs.append(obs_history.new_zeros((b, self.nwp_embed_dim, h, w)))

            if static_feat is not None:
                head_inputs.append(static_feat)

            combined_feat = torch.cat(head_inputs, dim=1) if len(head_inputs) > 1 else head_inputs[0]
            delta = self.lead_heads[h_idx](combined_feat)
            lead_outputs.append(delta)

        return torch.stack(lead_outputs, dim=1)

    def forward(
        self,
        inputs: torch.Tensor | None = None,
        persistence_baseline: torch.Tensor | None = None,
        missing_channel_mask: torch.Tensor | None = None,
        *,
        obs_history: torch.Tensor | None = None,
        nwp_future: torch.Tensor | None = None,
        static_features: torch.Tensor | None = None,
        missing_obs_mask: torch.Tensor | None = None,
        missing_nwp_mask: torch.Tensor | None = None,
        missing_static_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if persistence_baseline is None:
            if obs_history is not None:
                persistence_baseline = obs_history[:, -1, 0:1]
            elif inputs is not None:
                persistence_baseline = inputs[:, -1, 0:1]
            else:
                raise ValueError("Must provide persistence_baseline or inputs/obs_history.")

        residual = self.predict_residual(
            inputs=inputs,
            missing_mask=missing_channel_mask,
            obs_history=obs_history,
            nwp_future=nwp_future,
            static_features=static_features,
            missing_obs_mask=missing_obs_mask,
            missing_nwp_mask=missing_nwp_mask,
            missing_static_mask=missing_static_mask,
        )
        return reconstruct_persistence_residual(persistence_baseline, residual)
