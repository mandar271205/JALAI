"""Audit a completed Phase 4E raw GFS corpus; never downloads data."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.gfs_replay.phase4e_audit import audit_download
from jalrakshak_ml.gfs_replay.rich_pipeline import plan_rich_replay_for_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"
    )
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--output", default="reports/phase4e_rich_gfs_download_audit.json")
    args = parser.parse_args()
    cfg = load_yaml(args.config)
    plan = plan_rich_replay_for_events(cfg["events"], cfg["temporal"]["assumed_latency_hours"])
    result = audit_download(plan, args.cache_root)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}, indent=2))


if __name__ == "__main__":
    main()
