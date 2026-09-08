"""Multi-Source Meteorological Tensor Builder and Versioned Store for JalRakshak AI.

Assembles aligned multi-channel tensors for future deep nowcasting & NWP fusion
models. Supports:
- Complete mode (strictly requires all specified channels)
- Degraded mode (allows missing sources, masking missing channels with valid_mask=False)
- Source dropout mode (randomly drops available sources during training research)
- Explicit fallback policy hierarchy (Radar -> Satellite -> GPM)
- Versioned storage with manifest tracking
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from jalrakshak_ml.weather.contracts import MeteorologicalField

log = logging.getLogger(__name__)

# Standard multi-source channel catalog
CANONICAL_CHANNELS = (
    "rainfall_gpm",
    "radar_reflectivity",
    "radar_rainfall",
    "satellite_ir",
    "satellite_wv",
    "gfs_precipitation",
    "gfs_u10",
    "gfs_v10",
    "gfs_rh2m",
    "gfs_t2m",
    "gfs_cape",
)

# Robust channel-specific normalization statistics (estimated from physical ranges or non-test data)
DEFAULT_NORMALIZATION_STATS: dict[str, dict[str, float]] = {
    "rainfall_gpm": {"mean": 1.5, "std": 4.0, "min": 0.0, "max": 150.0, "scale": 1.0 / 50.0},
    "radar_reflectivity": {"mean": 20.0, "std": 15.0, "min": -10.0, "max": 70.0, "scale": 1.0 / 70.0},
    "radar_rainfall": {"mean": 2.0, "std": 5.0, "min": 0.0, "max": 150.0, "scale": 1.0 / 50.0},
    "satellite_ir": {"mean": 270.0, "std": 20.0, "min": 190.0, "max": 320.0, "scale": 1.0 / 100.0},
    "satellite_wv": {"mean": 240.0, "std": 15.0, "min": 190.0, "max": 280.0, "scale": 1.0 / 100.0},
    "gfs_precipitation": {"mean": 1.2, "std": 3.5, "min": 0.0, "max": 100.0, "scale": 1.0 / 50.0},
    "gfs_u10": {"mean": 5.0, "std": 4.0, "min": -30.0, "max": 30.0, "scale": 1.0 / 20.0},
    "gfs_v10": {"mean": 2.0, "std": 4.0, "min": -30.0, "max": 30.0, "scale": 1.0 / 20.0},
    "gfs_rh2m": {"mean": 85.0, "std": 10.0, "min": 0.0, "max": 100.0, "scale": 1.0 / 100.0},
    "gfs_t2m": {"mean": 298.0, "std": 3.0, "min": 280.0, "max": 315.0, "scale": 1.0 / 30.0},
    "gfs_cape": {"mean": 800.0, "std": 600.0, "min": 0.0, "max": 5000.0, "scale": 1.0 / 2500.0},
}


@dataclass(slots=True)
class MultiSourceTensor:
    """Multi-channel aligned meteorological input tensor for neural models."""

    data: np.ndarray                         # Shape: (channels, y, x), float32
    valid_mask: np.ndarray                   # Shape: (channels, y, x), bool
    missing_channel_mask: np.ndarray         # Shape: (channels,), bool (True if channel absent)
    channel_names: list[str]
    issue_time: datetime
    source_age_minutes: dict[str, float]
    provenance: dict[str, Any] = field(default_factory=dict)
    normalization_metadata: dict[str, Any] = field(default_factory=dict)
    fallback_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_names": self.channel_names,
            "shape": list(self.data.shape),
            "issue_time": self.issue_time.isoformat(),
            "missing_channels": [
                name for name, is_missing in zip(self.channel_names, self.missing_channel_mask) if is_missing
            ],
            "present_channels": [
                name for name, is_missing in zip(self.channel_names, self.missing_channel_mask) if not is_missing
            ],
            "source_age_minutes": self.source_age_minutes,
            "fallback_metadata": self.fallback_metadata,
            "provenance": self.provenance,
        }


class MultiSourceTensorBuilder:
    """Builds aligned multi-channel tensors from available MeteorologicalField objects."""

    def __init__(
        self,
        channels: Sequence[str] = CANONICAL_CHANNELS,
        target_shape: tuple[int, int] = (256, 256),
        normalization: str = "scale",
        rng_seed: int = 26071,
    ) -> None:
        self.channels = list(channels)
        self.target_shape = target_shape
        self.normalization = normalization
        self.rng = np.random.default_rng(rng_seed)

    def build(
        self,
        fields_by_channel: dict[str, MeteorologicalField],
        issue_time: datetime,
        mode: str = "degraded",
        dropout_prob: float = 0.0,
    ) -> MultiSourceTensor:
        """Assemble multi-source tensor.

        Parameters
        ----------
        fields_by_channel : dict[str, MeteorologicalField]
            Mapping of channel name to canonical field instance.
        issue_time : datetime
            Simulated issue timestamp.
        mode : str
            "complete" (fails if any channel is missing) or "degraded" (allows missing).
        dropout_prob : float
            Probability of dropping an available channel (for training robustness).
        """
        c = len(self.channels)
        h, w = self.target_shape

        data_tensor = np.zeros((c, h, w), dtype=np.float32)
        valid_tensor = np.zeros((c, h, w), dtype=bool)
        missing_mask = np.zeros(c, dtype=bool)
        age_dict: dict[str, float] = {}

        for idx, chan in enumerate(self.channels):
            if chan not in fields_by_channel:
                if mode == "complete":
                    raise KeyError(f"Required channel {chan!r} is missing in complete mode.")
                missing_mask[idx] = True
                continue

            field_item = fields_by_channel[chan]
            if field_item.data.shape != (h, w):
                raise ValueError(
                    f"Channel {chan} shape {field_item.data.shape} does not match target ({h}, {w})"
                )

            # Apply training source dropout if requested
            if dropout_prob > 0.0 and self.rng.random() < dropout_prob:
                missing_mask[idx] = True
                continue

            raw_data = np.copy(field_item.data)
            vmask = np.copy(field_item.valid_mask)

            # Normalize if configured
            if self.normalization == "scale" and chan in DEFAULT_NORMALIZATION_STATS:
                stats = DEFAULT_NORMALIZATION_STATS[chan]
                scaled = raw_data * stats["scale"]
                data_tensor[idx] = np.where(vmask, scaled, 0.0)
            else:
                data_tensor[idx] = np.where(vmask, raw_data, 0.0)

            valid_tensor[idx] = vmask
            missing_mask[idx] = False

            # Compute source age
            target_t = field_item.observation_time or field_item.valid_time
            age_dict[chan] = (issue_time - target_t).total_seconds() / 60.0

        # Execute fallback resolution logic for observation
        fallback_meta = self._resolve_fallback(fields_by_channel)

        return MultiSourceTensor(
            data=data_tensor,
            valid_mask=valid_tensor,
            missing_channel_mask=missing_mask,
            channel_names=self.channels,
            issue_time=issue_time,
            source_age_minutes=age_dict,
            normalization_metadata={
                "method": self.normalization,
                "stats": {k: DEFAULT_NORMALIZATION_STATS[k] for k in self.channels if k in DEFAULT_NORMALIZATION_STATS},
            },
            fallback_metadata=fallback_meta,
            provenance={
                "builder": "MultiSourceTensorBuilder_v1",
                "mode": mode,
                "dropout_prob": dropout_prob,
            },
        )

    def _resolve_fallback(
        self, fields: dict[str, MeteorologicalField]
    ) -> dict[str, Any]:
        """Audit active observation source and trace hierarchical fallback."""
        radar_present = "radar_rainfall" in fields or "radar_reflectivity" in fields
        satellite_present = "satellite_ir" in fields or "satellite_wv" in fields
        gpm_present = "rainfall_gpm" in fields
        gfs_present = any(c.startswith("gfs_") for c in fields)

        if radar_present:
            primary_obs = "radar"
            fallback_used = False
        elif satellite_present:
            primary_obs = "satellite"
            fallback_used = True
        elif gpm_present:
            primary_obs = "gpm"
            fallback_used = True
        else:
            primary_obs = "none"
            fallback_used = False

        return {
            "primary_observation_source": primary_obs,
            "fallback_used": fallback_used,
            "radar_available": radar_present,
            "satellite_available": satellite_present,
            "gpm_available": gpm_present,
            "nwp_guidance_available": gfs_present,
            "active_channels": list(fields.keys()),
        }


def save_multisource_store(
    tensor: MultiSourceTensor,
    store_root: Path | str,
    event_id: str,
    data_version: str = "v1",
) -> tuple[Path, dict[str, Any]]:
    """Save multi-source tensor and manifest to versioned store.

    Only present variables are populated. No fake zeros in unavailable stores.
    """
    out_dir = Path(store_root) / data_version / event_id / tensor.issue_time.strftime("%Y%m%dT%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)

    array_path = out_dir / "tensors.npz"
    meta_path = out_dir / "metadata.json"

    # Save arrays
    np.savez_compressed(
        array_path,
        data=tensor.data,
        valid_mask=tensor.valid_mask,
        missing_channel_mask=tensor.missing_channel_mask,
    )

    manifest = {
        "event_id": event_id,
        "data_version": data_version,
        "issue_time": tensor.issue_time.isoformat(),
        "array_file": array_path.name,
        **tensor.to_dict(),
    }
    meta_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_dir, manifest
