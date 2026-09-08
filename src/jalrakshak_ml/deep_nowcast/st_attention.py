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

from jalrakshak_ml.deep_nowcast.residual_convlstm import reconstruct_persistence_residual


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
    """Spatiotemporal Attention Nowcaster V1."""

    model_version = "st_attention_nowcaster_v1"
    forecast_mode = "persistence_residual_multisource"

    def __init__(
        self,
        *,
        input_channels: int = 3,
        embed_dim: int = 64,
        num_heads: int = 4,
        patch_size: int = 8,
        output_horizons: int = 4,
        head_channels: int = 16,
    ):
        super().__init__()
        self.input_channels = input_channels
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.patch_size = patch_size
        self.output_horizons = output_horizons
        self.head_channels = head_channels

        # Patch embedding stem: [C_in, 128, 128] -> [embed_dim, 16, 16]
        self.patch_embed = nn.Conv2d(
            input_channels,
            embed_dim,
            kernel_size=patch_size,
            stride=patch_size,
        )
        self.pos_embed = nn.Parameter(torch.zeros(1, (128 // patch_size) ** 2, embed_dim))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)

        # Spatiotemporal attention layers
        self.spatial_attn = SpatialAttentionBlock(embed_dim=embed_dim, num_heads=num_heads)
        self.temporal_attn = TemporalAttentionBlock(embed_dim=embed_dim, num_heads=num_heads)

        # Temporal aggregation projection: aggregate T tokens to 1 feature map
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

        # 4 Lead-specific heads at 128x128
        self.lead_heads = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(16, head_channels, kernel_size=3, padding=1),
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
            "embed_dim": self.embed_dim,
            "num_heads": self.num_heads,
            "patch_size": self.patch_size,
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

        # Flatten B and T to patch-embed: [B * T, C, H, W]
        x = inputs.view(b * t, c, h, w)
        patches = self.patch_embed(x)                      # [B * T, D, H/P, W/P]
        _, d, ph, pw = patches.shape
        n_tokens = ph * pw

        # Reshape to token sequence: [B * T, N, D]
        tokens = patches.flatten(2).transpose(1, 2)
        tokens = tokens + self.pos_embed

        # 1. Spatial attention
        tokens = self.spatial_attn(tokens)

        # 2. Temporal attention
        tokens = self.temporal_attn(tokens, b, t, n_tokens)

        # 3. Temporal aggregation: [B, T, N, D] -> [B, N, T * D] -> [B, N, D]
        tokens_bt = tokens.view(b, t, n_tokens, d).permute(0, 2, 1, 3).reshape(b, n_tokens, t * d)
        tokens_agg = self.time_agg(tokens_bt)             # [B, N, D]

        # Reshape to 2D feature map [B, D, ph, pw]
        feat_map = tokens_agg.transpose(1, 2).contiguous().view(b, d, ph, pw)


        # 4. Decoder upsampling to 128x128
        dec_feat = self.decoder(feat_map)                 # [B, 16, 128, 128]

        # 5. Lead-specific heads
        lead_outputs = []
        for head in self.lead_heads:
            delta = head(dec_feat)                        # [B, 1, 128, 128]
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
