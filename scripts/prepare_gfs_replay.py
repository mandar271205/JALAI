"""Plan/materialize benchmark timestamps, or explicitly prepare Phase 4A replay data."""

import argparse
import json

from jalrakshak_ml.gfs_replay.pipeline import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/replay/gfs_mumbai_v1.yaml")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--download", action="store_true", help="Permit bounded PRATE range downloads"
    )
    args = parser.parse_args()
    if args.download and not args.execute:
        parser.error("--download requires --execute")
    print(json.dumps(prepare(args.config, execute=args.execute, download=args.download), indent=2))


if __name__ == "__main__":
    main()
