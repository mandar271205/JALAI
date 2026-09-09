"""Spatiotemporal Attention Nowcaster (STAttentionNowcasterV1).

A compact, computationally efficient spatiotemporal transformer-style model:
- Patch embedding stem (8x8 non-overlapping spatial patches)
- Spatial Multi-Head Self-Attention per timestep
- Temporal Multi-Head Attention across time steps
- Multi-scale convolutional decoder with skip reconstruction
- 4 Lead-specific forecast heads
- Physical persistence residual formulation
"""
from __future__ import annotations

from typing import Any

import torch
from torch import nn

from jalrakshak_ml.deep_nowcast.final_contracts import (
    differentiable_nonnegative,
    validate_separated_inputs,
)


class SpatialAttentionBlock(nn.Module):
    """Multi-Head Self-Attention over spatial tokens."""

    def __init__(self, embed_dim: int = 64, num_heads: int = 4, mlp_ratio: float = 2.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(embed_dim)
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(embed_dim)
        mlp_hidden = int(embed_dim * mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim, mlp_hidden),
            nn.GELU(),
            nn.Linear(mlp_hidden, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B * T, N_tokens, embed_dim]"""
        norm_x = self.norm1(x)
        attn_out, _ = self.attn(norm_x, norm_x, norm_x)
        x = x + attn_out
        x = x + self.mlp(self.norm2(x))
        return x


class TemporalAttentionBlock(nn.Module):
    """Multi-Head Attention across time steps for each spatial token."""

    def __init__(self, embed_dim: int = 64, num_heads: int = 4):
        super().__init__()
        self.norm1 = nn.LayerNorm(embed_dim)
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(embed_dim)
        self.mlp = nn.Sequential(
            nn.Linear(embed_dim, embed_dim * 2),
            nn.GELU(),
            nn.Linear(embed_dim * 2, embed_dim),
        )

    def forward(self, x: torch.Tensor, b: int, t: int, n: int) -> torch.Tensor:
        """x: [B * T, N, D] -> reshape to [B * N, T, D] -> attend over T -> back."""
        d = x.shape[-1]
        # [B, T, N, D] -> [B, N, T, D] -> [B * N, T, D]
        xt = x.view(b, t, n, d).permute(0, 2, 1, 3).reshape(b * n, t, d)
        norm_xt = self.norm1(xt)
        attn_out, _ = self.attn(norm_xt, norm_xt, norm_xt)
        xt = xt + attn_out
        xt = xt + self.mlp(self.norm2(xt))
        # [B * N, T, D] -> [B, N, T, D] -> [B, T, N, D] -> [B * T, N, D]
        x_out = xt.view(b, n, t, d).permute(0, 2, 1, 3).reshape(b * t, n, d)
        return x_out


class STAttentionNowcasterV1(nn.Module):
    """Spatiotemporal Attention Nowcaster V1 with decoupled NWP horizon and static encoders."""

    model_version = "st_attention_nowcaster_v1"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        obs_channels: int | None = None,
        nwp_channels: int | None = None,
        static_channels: int | None = None,
        embed_dim: int = 64,
        num_heads: int = 4,
        patch_size: int = 8,
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
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.patch_size = patch_size
        self.output_horizons = output_horizons
        self.head_channels = head_channels
        self.nwp_embed_dim = nwp_embed_dim if nwp_channels > 0 else 0
        self.static_embed_dim = static_embed_dim if static_channels > 0 else 0

        # 1. Observation sequence encoder (historical GPM sequence)
        self.patch_embed = nn.Conv2d(
            obs_channels,
            embed_dim,
            kernel_size=patch_size,
            stride=patch_size,
        )
        self.pos_embed = nn.Parameter(torch.zeros(1, (128 // patch_size) ** 2, embed_dim))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)

        # Spatiotemporal attention layers
        self.spatial_attn = SpatialAttentionBlock(embed_dim=embed_dim, num_heads=num_heads)
        self.temporal_attn = TemporalAttentionBlock(embed_dim=embed_dim, num_heads=num_heads)

        # Temporal aggregation projection: aggregate T_obs tokens to 1 feature map
        self.time_agg = nn.Linear(4 * embed_dim, embed_dim)

        # Convolutional decoder upsampling: 16x16 -> 32x32 -> 64x64 -> 128x128
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(embed_dim, 32, kernel_size=2, stride=2),  # 32x32
            nn.BatchNorm2d(32),
            nn.GELU(),
            nn.ConvTranspose2d(32, 24, kernel_size=2, stride=2),         # 64x64
            nn.BatchNorm2d(24),
            nn.GELU(),
            nn.ConvTranspose2d(24, 16, kernel_size=2, stride=2),         # 128x128
            nn.BatchNorm2d(16),
            nn.GELU(),
        )

        # 2. NWP horizon encoder (encodes future NWP per horizon)
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

        # 4. Lead-specific heads at 128x128
        combined_dim = 16 + self.nwp_embed_dim + self.static_embed_dim
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
            "embed_dim": self.embed_dim,
            "num_heads": self.num_heads,
            "patch_size": self.patch_size,
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
        elif self.nwp_channels == 11 and self.static_channels == 1:
            if nwp_future is None or static_features is None:
                raise ValueError("Final Phase 4E models require NWP and static sources explicitly")
            validate_separated_inputs(obs_history, nwp_future, static_features)

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

        # Flatten B and T to patch-embed observation sequence: [B * T_obs, C_obs, H, W]
        x = obs_history.view(b * t_obs, self.obs_channels, h, w)
        patches = self.patch_embed(x)                      # [B * T_obs, D, H/P, W/P]
        _, d, ph, pw = patches.shape
        n_tokens = ph * pw

        # Reshape to token sequence: [B * T_obs, N, D]
        tokens = patches.flatten(2).transpose(1, 2)
        tokens = tokens + self.pos_embed

        # 1. Spatial attention
        tokens = self.spatial_attn(tokens)

        # 2. Temporal attention
        tokens = self.temporal_attn(tokens, b, t_obs, n_tokens)

        # 3. Temporal aggregation: [B, T_obs, N, D] -> [B, N, T_obs * D] -> [B, N, D]
        tokens_bt = tokens.view(b, t_obs, n_tokens, d).permute(0, 2, 1, 3).reshape(b, n_tokens, t_obs * d)
        tokens_agg = self.time_agg(tokens_bt)              # [B, N, D]

        # Reshape to 2D feature map [B, D, ph, pw]
        feat_map = tokens_agg.transpose(1, 2).contiguous().view(b, d, ph, pw)

        # 4. Decoder upsampling to 128x128
        dec_feat = self.decoder(feat_map)                  # [B, 16, 128, 128]

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
            head_inputs = [dec_feat]

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
        if obs_history is not None and nwp_future is not None and static_features is not None:
            validate_separated_inputs(
                obs_history, nwp_future, static_features, persistence_baseline
            )
        baseline = persistence_baseline[:, None]
        return differentiable_nonnegative(baseline + residual)
