"""Small text/metadata-only reproducibility bundle builder."""

from __future__ import annotations

import hashlib
import shutil
from importlib import metadata
from pathlib import Path
from typing import Any

from .common import atomic_immutable_json, canonical_hash
from .run_manifest import cuda_metadata, local_machine_metadata

ALLOWED_SUFFIXES = {".json", ".yaml", ".yml", ".md", ".txt", ".csv", ".toml"}
BLOCKED_PARTS = {"raw", "secrets", ".git", "checkpoints", "zarr", "grib", "credentials"}
MAX_FILE_BYTES = 1_000_000


def _safe_metadata_file(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return (
        path.is_file()
        and path.suffix.lower() in ALLOWED_SUFFIXES
        and not lowered.intersection(BLOCKED_PARTS)
        and path.stat().st_size <= MAX_FILE_BYTES
    )


def build_reproducibility_bundle(
    *,
    destination: str | Path,
    repo_root: str | Path,
    files: list[str | Path],
    git_commit: str,
    git_status: str,
    references: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    dest = Path(destination)
    if dest.exists():
        raise FileExistsError("Reproducibility bundles are immutable")
    dest.mkdir(parents=True)
    copied: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for supplied in files:
        source = (
            (root / supplied).resolve()
            if not Path(supplied).is_absolute()
            else Path(supplied).resolve()
        )
        try:
            relative = source.relative_to(root)
        except ValueError:
            excluded.append({"path": str(supplied), "reason": "outside_repository"})
            continue
        if not _safe_metadata_file(source):
            excluded.append(
                {"path": relative.as_posix(), "reason": "raw_large_secret_or_unsupported"}
            )
            continue
        target = dest / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "bytes": source.stat().st_size,
            }
        )
    dependencies = {}
    for package in ("numpy", "pandas", "pydantic", "PyYAML", "torch", "scikit-learn"):
        try:
            dependencies[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            dependencies[package] = "NOT_INSTALLED"
    manifest = {
        "bundle_version": "phase8_metadata_bundle_v1",
        "git_commit": git_commit,
        "git_status": git_status,
        "machine": local_machine_metadata(),
        "cuda": cuda_metadata(),
        "dependencies": dependencies,
        "included_files": copied,
        "excluded_files": excluded,
        "references": references or {},
        "raw_data_included": False,
        "model_checkpoints_included": False,
        "credentials_included": False,
    }
    manifest["bundle_sha256"] = canonical_hash(manifest)
    return atomic_immutable_json(dest / "bundle_manifest.json", manifest)
