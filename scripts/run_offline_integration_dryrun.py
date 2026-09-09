"""Run the fixture-only Phase 8 integration path without locked-test access."""

import argparse
import json
import subprocess
from pathlib import Path

from jalrakshak_ml.research.integration import run_offline_dryrun


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New immutable run manifest")
    args = parser.parse_args()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    print(json.dumps(run_offline_dryrun(args.output, git_sha=sha), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
