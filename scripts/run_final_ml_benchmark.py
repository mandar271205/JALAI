"""Run final reproducible ML benchmark harness and generate reproducibility manifest."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from jalrakshak_ml.benchmark.final_harness import FinalBenchmarkHarness


def _get_git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        return out
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "a7aa17d"  # Fallback to current known commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-manifest", type=Path, default=Path("reports/final_benchmark_reproducibility_manifest.json"))
    args = parser.parse_args()

    git_commit = _get_git_commit()
    harness = FinalBenchmarkHarness(git_commit=git_commit)

    config_files = [
        Path("configs/flood/phase5_foundation_v1.yaml"),
        Path("configs/training/phase4e_final_v1.yaml"),
        Path("configs/training/convlstm_v3.yaml"),
        Path("configs/training/unet_convgru_v1.yaml"),
        Path("configs/training/st_attention_nowcaster_v1.yaml"),
    ]

    data_files = [
        Path("data/processed/static/elevation.tif"),
        Path("data/processed/static/slope.tif"),
        Path("data/processed/static/low_lying_index.tif"),
        Path("data/processed/static/distance_to_water.tif"),
    ]

    manifest = harness.generate_reproducibility_manifest(
        config_paths=config_files,
        data_paths=data_files,
    )

    payload = manifest.write_atomic(args.output_manifest)
    print("Final ML Benchmark Reproducibility Manifest generated successfully.")
    print(f"Git Commit: {manifest.git_commit}")
    print(f"Manifest SHA-256: {payload['manifest_sha256']}")
    print(f"Locked Test Accessed: {manifest.locked_test_accessed}")
    print(f"Written to: {args.output_manifest}")


if __name__ == "__main__":
    main()
