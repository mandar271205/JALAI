"""Small deterministic helpers shared by Phase 8 contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def atomic_immutable_json(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"Immutable artifact already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    part.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(destination)
    return payload
