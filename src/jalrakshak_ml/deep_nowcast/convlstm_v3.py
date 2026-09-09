"""ConvLSTM V3 Nowcaster with Multi-Source Encoder, Spatial Feature Extractor, and Lead-Specific Heads."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import torch
from torch import nn

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMCell
from jalrakshak_ml.deep_nowcast.final_contracts import (
    differentiable_nonnegative,
    validate_separated_inputs,
)


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
    """ConvLSTM V3: Decoupled observation encoder, NWP horizon encoder, static encoder, and lead-specific heads."""

    model_version = "convlstm_v3"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        obs_channels: int | None = None,
        nwp_channels: int | None = None,
        static_channels: int | None = None,
        hidden_channels: int | Sequence[int] = (24, 24),
        output_horizons: int = 4,
        kernel_size: int = 3,
        head_channels: int = 16,
        nwp_embed_dim: int = 8,
        static_embed_dim: int = 4,
    ):
        super().__init__()
        if isinstance(hidden_channels, int):
            hidden = [hidden_channels, hidden_channels]
        else:
            hidden = [int(h) for h in hidden_channels]

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
        self.hidden_channels = hidden
        self.output_horizons = output_horizons
        self.head_channels = head_channels
        self.nwp_embed_dim = nwp_embed_dim if nwp_channels > 0 else 0
        self.static_embed_dim = static_embed_dim if static_channels > 0 else 0

        # 1. Observation sequence encoder (encodes historical GPM sequence)
        base_features = hidden[0]
        self.obs_encoder = MultiSourceEncoder(obs_channels, base_features)
        self.spatial_block = MultiScaleSpatialBlock(base_features)

        # 2. ConvLSTM temporal core over observation history
        cells = []
        prev = base_features
        for ch in hidden:
            cells.append(ConvLSTMCell(prev, ch, kernel_size=kernel_size))
            prev = ch
        self.cells = nn.ModuleList(cells)

        # 3. NWP horizon encoder (encodes future meteorological feature maps per horizon)
        if self.nwp_channels > 0 and self.nwp_embed_dim > 0:
            self.nwp_encoder = nn.Sequential(
                nn.Conv2d(self.nwp_channels, self.nwp_embed_dim, kernel_size=3, padding=1),
                nn.BatchNorm2d(self.nwp_embed_dim),
                nn.GELU(),
            )
        else:
            self.nwp_encoder = None

        # 4. Static encoder (encodes DEM once)
        if self.static_channels > 0 and self.static_embed_dim > 0:
            self.static_encoder = nn.Sequential(
                nn.Conv2d(self.static_channels, self.static_embed_dim, kernel_size=3, padding=1),
                nn.BatchNorm2d(self.static_embed_dim),
                nn.GELU(),
            )
        else:
            self.static_encoder = None

        # 5. Lead-specific forecast heads combining obs, horizon NWP, and static representations
        combined_dim = hidden[-1] + self.nwp_embed_dim + self.static_embed_dim
        self.lead_heads = nn.ModuleList([
            LeadSpecificHead(combined_dim, head_channels=head_channels, horizon_idx=i)
            for i in range(output_horizons)
        ])

    def config_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "forecast_mode": self.forecast_mode,
            "input_channels": self.input_channels,
            "obs_channels": self.obs_channels,
            "nwp_channels": self.nwp_channels,
            "static_channels": self.static_channels,
            "hidden_channels": list(self.hidden_channels),
            "output_horizons": self.output_horizons,
            "head_channels": self.head_channels,
            "nwp_embed_dim": self.nwp_embed_dim,
            "static_embed_dim": self.static_embed_dim,
        }

    def _split_inputs(
        self, inputs: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor | None, torch.Tensor | None]:
        """Split legacy single-tensor inputs [B, T, C, H, W] into decoupled components."""
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
        """Predict horizon-specific signed rainfall residuals using decoupled conditioning.

        Parameters:
        obs_history: [B, T_hist, C_obs, H, W]
        nwp_future: [B, T_future, C_nwp, H, W] or None
        static_features: [B, C_static, H, W] or None
        inputs: [B, T, C, H, W] legacy fallback
        """
        if obs_history is None:
            if inputs is None:
                raise ValueError("Either obs_history or inputs must be provided.")
            obs_history, nwp_future, static_features = self._split_inputs(inputs)
        elif self.nwp_channels == 11 and self.static_channels == 1:
            if nwp_future is None or static_features is None:
                raise ValueError("Final Phase 4E models require NWP and static sources explicitly")
            validate_separated_inputs(obs_history, nwp_future, static_features)

        b, t_obs, _, h, w = obs_history.shape

        # Resolve masks if legacy single missing_mask passed
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

        # 1. Observation sequence encoder through ConvLSTM core
        states = [
            (
                obs_history.new_zeros((b, hid, h, w)),
                obs_history.new_zeros((b, hid, h, w)),
            )
            for hid in self.hidden_channels
        ]

        for step in range(t_obs):
            step_in = obs_history[:, step]  # [B, C_obs, H, W]
            feat = self.obs_encoder(step_in, missing_mask=missing_obs_mask)
            feat = self.spatial_block(feat)

            layer_input = feat
            for l_idx, cell in enumerate(self.cells):
                states[l_idx] = cell(layer_input, states[l_idx])
                layer_input = states[l_idx][0]

        last_hidden = states[-1][0]  # [B, hidden[-1], H, W]

        # 2. Static encoder representation (DEM encoded once)
        if self.static_encoder is not None and static_features is not None:
            if missing_static_mask is not None:
                s_gate = (~missing_static_mask).to(dtype=static_features.dtype).view(b, -1, 1, 1)
                static_in = static_features * s_gate
            else:
                static_in = static_features
            static_feat = self.static_encoder(static_in)  # [B, static_embed_dim, H, W]
        elif self.static_embed_dim > 0:
            static_feat = obs_history.new_zeros((b, self.static_embed_dim, h, w))
        else:
            static_feat = None

        # 3. NWP horizon encoder and lead-specific heads
        lead_outputs = []
        for h_idx in range(self.output_horizons):
            head_inputs = [last_hidden]

            if self.nwp_encoder is not None and nwp_future is not None:
                horizon_nwp = nwp_future[:, h_idx]  # [B, C_nwp, H, W]
                if missing_nwp_mask is not None:
                    n_gate = (~missing_nwp_mask).to(dtype=horizon_nwp.dtype).view(b, -1, 1, 1)
                    horizon_nwp = horizon_nwp * n_gate
                nwp_h_feat = self.nwp_encoder(horizon_nwp)  # [B, nwp_embed_dim, H, W]
                head_inputs.append(nwp_h_feat)
            elif self.nwp_embed_dim > 0:
                head_inputs.append(obs_history.new_zeros((b, self.nwp_embed_dim, h, w)))

            if static_feat is not None:
                head_inputs.append(static_feat)

            combined_feat = torch.cat(head_inputs, dim=1) if len(head_inputs) > 1 else head_inputs[0]
            delta = self.lead_heads[h_idx](combined_feat)  # [B, 1, H, W]
            lead_outputs.append(delta)

        # Stack into [B, output_horizons, 1, H, W]
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
        """Returns non-negative rainfall forecast [B, output_horizons, 1, H, W]."""
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
        if obs_history is not None and nwp_future is not None and static_features is not None:
            validate_separated_inputs(
                obs_history, nwp_future, static_features, persistence_baseline
            )
        baseline = persistence_baseline[:, None]
        return differentiable_nonnegative(baseline + residual)
