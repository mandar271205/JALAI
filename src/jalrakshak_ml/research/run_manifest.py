"""Immutable end-to-end run manifests."""

from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .common import atomic_immutable_json, canonical_hash


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    git_sha: str
    config_hashes: dict[str, str]
    source_hashes: dict[str, str]
    model_hashes: dict[str, str]
    normalization_hash: str | None
    data_split: dict[str, Any]
    started_at: str
    completed_at: str
    machine_device: dict[str, Any]
    cuda_info: dict[str, Any]
    random_seeds: dict[str, int]
    input_sources: list[dict[str, Any]]
    output_artifacts: list[dict[str, Any]]
    evaluation_metrics: list[dict[str, Any]]
    scientific_claim_gates: list[dict[str, Any]]
    locked_test_accessed: bool = False

    def validate(self) -> None:
        if self.locked_test_accessed:
            raise PermissionError("Locked test access is forbidden for this Phase 8 dry run")
        if not self.run_id or len(self.git_sha) < 7:
            raise ValueError("run_id and git SHA are required")
        if not self.config_hashes:
            raise ValueError("At least one config hash is required")

    def write(self, path: str | Path) -> dict[str, Any]:
        self.validate()
        body = asdict(self)
        body["manifest_sha256"] = canonical_hash(body)
        return atomic_immutable_json(path, body)


def local_machine_metadata() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
    }


def cuda_metadata() -> dict[str, Any]:
    try:
        import torch

        return {
            "torch_available": True,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_version": torch.version.cuda,
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        }
    except ImportError:
        return {
            "torch_available": False,
            "cuda_available": False,
            "cuda_version": None,
            "device_count": 0,
        }
