"""Audit completed Phase 4E rich replay integrity; never builds replay data."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.gfs_replay.phase4e_audit import audit_replay
from jalrakshak_ml.gfs_replay.rich_pipeline import plan_rich_replay_for_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"
    )
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--output", default="reports/phase4e_rich_replay_integrity_audit.json")
    args = parser.parse_args()
    cfg = load_yaml(args.config)
    plan = plan_rich_replay_for_events(cfg["events"], cfg["temporal"]["assumed_latency_hours"])
    result = audit_replay(plan, args.replay_root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
