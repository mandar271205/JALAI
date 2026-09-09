"""Build the 255 non-test rich replay issues from an already-audited raw cache."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.config import load_pilot_config, load_yaml
from jalrakshak_ml.gfs_replay.pipeline import build_target_grid
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    build_rich_issue_from_cache,
    plan_rich_replay_for_events,
    save_rich_issue,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml"
    )
    parser.add_argument("--raw-cache", required=True)
    parser.add_argument("--download-audit", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cfg = load_yaml(args.config)
    plan = plan_rich_replay_for_events(cfg["events"], cfg["temporal"]["assumed_latency_hours"])
    summary = {
        "events": plan["total_events"],
        "train_issues": plan["train_issues"],
        "validation_issues": plan["validation_issues"],
        "test_issues": 0,
        "total_issues": plan["total_issues"],
        "execution_state": "NOT_STARTED",
    }
    if not args.execute:
        print(json.dumps(summary, indent=2))
        return

    output_manifest = Path(args.output_root) / "manifest.json"
    if output_manifest.exists():
        raise FileExistsError(f"Versioned replay manifest already exists: {output_manifest}")

    audit = json.loads(Path(args.download_audit).read_text(encoding="utf-8"))
    expected_pairs = len(plan["unique_cycle_leads_required"])
    if not audit.get("audit_passed") or audit.get("complete_pairs") != expected_pairs:
        raise RuntimeError(
            f"Raw download audit gate is not satisfied: expected {expected_pairs} complete pairs, "
            f"got {audit.get('complete_pairs')}"
        )
    pilot = load_pilot_config("configs/pilot/mumbai.yaml")
    target = build_target_grid(
        bbox_wgs84=pilot["bbox_wgs84"],
        analysis_crs=pilot["analysis_crs"],
        width=pilot["grid"]["width"],
        height=pilot["grid"]["height"],
    )
    written = 0
    for event_id, event in plan["events"].items():
        for issue in event["issues"]:
            payload = build_rich_issue_from_cache(
                event_id, issue["issue_time"], issue["target_times"], args.raw_cache, target
            )
            save_rich_issue(args.output_root, payload)
            written += 1
    summary.update({"execution_state": "COMPLETE", "complete_issues": written})
    if output_manifest.exists():
        raise FileExistsError(f"Versioned replay manifest already exists: {output_manifest}")
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    part = output_manifest.with_suffix(output_manifest.suffix + ".part")
    part.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    part.replace(output_manifest)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
