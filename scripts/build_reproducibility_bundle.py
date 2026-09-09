"""Build a small metadata-only Phase 8 reproducibility bundle."""

import argparse
import json
import subprocess
from pathlib import Path

from jalrakshak_ml.research.reproducibility import build_reproducibility_bundle


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--include", action="append", default=[], help="Small metadata/config file")
    parser.add_argument("--references-json", type=Path, help="Data/model/source reference object")
    args = parser.parse_args()
    references = (
        json.loads(args.references_json.read_text(encoding="utf-8")) if args.references_json else {}
    )
    manifest = build_reproducibility_bundle(
        destination=args.destination,
        repo_root=args.repo_root,
        files=args.include,
        git_commit=_git("rev-parse", "HEAD"),
        git_status=_git("status", "--short"),
        references=references,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
