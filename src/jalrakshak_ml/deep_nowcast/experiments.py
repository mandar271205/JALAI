"""Pre-registered Phase 4E ablation and missing-source stress-test policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch

from .final_contracts import NWP_CHANNEL_ORDER

WIND_CHANNELS = (
    "gfs_u10",
    "gfs_v10",
    "gfs_wind_speed",
    "gfs_wind_direction_sin",
    "gfs_wind_direction_cos",
)
THERMODYNAMIC_CHANNELS = (
    "gfs_t2m",
    "gfs_rh2m",
    "gfs_surface_pressure",
    "gfs_cape",
    "gfs_pwat",
)
ABLATIONS: dict[str, dict[str, Any]] = {
    "A_remove_gfs_precipitation": {"nwp": ("gfs_precipitation",)},
    "B_remove_wind_group": {"nwp": WIND_CHANNELS},
    "C_remove_thermodynamic_group": {"nwp": THERMODYNAMIC_CHANNELS},
    "D_remove_terrain": {"static": True},
    "E_observation_only": {"nwp": NWP_CHANNEL_ORDER, "static": True},
    "F_nwp_only": {"observation": True, "static": True},
}
SOURCE_STRESS_TESTS = {
    "observation_unavailable": {"observation": True},
    "nwp_unavailable": {"nwp": NWP_CHANNEL_ORDER},
    "terrain_unavailable": {"static": True},
}


@dataclass(frozen=True)
class MaskedBatch:
    tensors: dict[str, torch.Tensor]
    metadata: dict[str, Any]


def apply_declared_mask(
    batch: dict[str, torch.Tensor],
    policy_name: str,
    *,
    training_policy: bool,
) -> MaskedBatch:
    """Apply an explicit zero mask; zeros are marked unavailable, never real values."""
    policies = ABLATIONS | SOURCE_STRESS_TESTS
    if policy_name not in policies:
        raise KeyError(f"Unknown policy: {policy_name}")
    policy = policies[policy_name]
    output = {
        key: value.clone() if isinstance(value, torch.Tensor) else value
        for key, value in batch.items()
    }
    masked_channels: list[str] = []
    if policy.get("observation"):
        output["obs_history"].zero_()
        output["persistence_baseline"].zero_()
        output["missing_obs_mask"].fill_(True)
        masked_channels.append("rainfall_gpm")
    if "nwp" in policy:
        for name in policy["nwp"]:
            position = NWP_CHANNEL_ORDER.index(name)
            output["nwp_future"][:, :, position].zero_()
            output["missing_nwp_mask"][:, position] = True
            masked_channels.append(name)
    if policy.get("static"):
        output["static_features"].zero_()
        output["missing_static_mask"].fill_(True)
        masked_channels.append("static_elevation")
    return MaskedBatch(
        output,
        {
            "policy_name": policy_name,
            "masked_channels": masked_channels,
            "zero_is_mask_not_measurement": True,
            "model_trained_with_policy": training_policy,
            "evaluation_missing_source_stress_test": not training_policy,
            "replacement_information_used": False,
        },
    )
