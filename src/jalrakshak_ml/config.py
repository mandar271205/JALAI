from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_pilot_config(path: str | Path = "configs/pilot/mumbai.yaml") -> dict[str, Any]:
    cfg = load_yaml(path)
    if "pilot" not in cfg:
        raise ValueError("Pilot config must contain a top-level 'pilot' key.")
    pilot = cfg["pilot"]

    bbox = pilot["bbox_wgs84"]
    if len(bbox) != 4:
        raise ValueError("bbox_wgs84 must be [west, south, east, north].")
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise ValueError("Invalid bbox ordering.")

    grid = pilot["grid"]
    if grid["width"] <= 0 or grid["height"] <= 0:
        raise ValueError("Grid dimensions must be positive.")

    return pilot
