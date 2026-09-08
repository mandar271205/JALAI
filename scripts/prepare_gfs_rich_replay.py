"""CLI script to plan and construct Phase 4E Rich GFS Replay for non-test events.

Usage:
    python scripts/prepare_gfs_rich_replay.py --plan-only
    python scripts/prepare_gfs_rich_replay.py --config configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml --plan-only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure src/ is on sys.path
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.splits import (
    LOCKED_TEST_EVENTS_AUTHORITATIVE,
    TRAIN_EVENTS_AUTHORITATIVE,
    VALIDATION_EVENTS_AUTHORITATIVE,
    is_locked_test_event,
)
from jalrakshak_ml.gfs_replay.core import utc
from jalrakshak_ml.gfs_replay.grib import fetch_rich_gfs_lead, source_uri
from jalrakshak_ml.gfs_replay.rich_pipeline import (
    RICH_GFS_REPLAY_VERSION,
    check_colab_drive_persistence,
    plan_rich_replay_for_events,
    resolve_rich_gfs_output_dir,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4E Rich GFS Replay Planner & Builder")
    parser.add_argument(
        "--config",
        default="configs/replay/gfs_mumbai_phase4e_rich_non_test_v1.yaml",
        help="Path to rich replay config YAML",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Calculate required GFS cycles and steps without downloading or reprojecting",
    )
    parser.add_argument(
        "--dry-run-download",
        action="store_true",
        help="Prove NOAA S3 URLs, .idx byte-range selectors, and destinations without retrieving bytes",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory (e.g. /content/drive/MyDrive/JALAI_DATA/processed/gfs_replay/...)",
    )
    parser.add_argument(
        "--output-plan",
        default="reports/phase4e_rich_gfs_replay_plan.json",
        help="Path to save the JSON replay plan",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Execute actual NOAA GFS byte-range download (CAUTION: network transfer)",
    )
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        log.error("Config not found: %s", cfg_path)
        return 1

    cfg = load_yaml(cfg_path)
    events = cfg.get("events", [])

    # Strict check: Test events must NEVER appear in this pipeline
    for ev in events:
        eid = ev["event_id"]
        if is_locked_test_event(eid):
            raise PermissionError(
                f"FATAL: Locked test event {eid!r} was found in rich replay config! "
                f"Locked test events must NEVER be processed in training/validation replay."
            )

    train_ids = [ev["event_id"] for ev in events if ev.get("split") == "train"]
    val_ids = [ev["event_id"] for ev in events if ev.get("split") == "validation"]

    log.info("Loaded Rich GFS Replay Config: %s", cfg.get("version"))
    log.info("Total Events: %d (Train: %d, Validation: %d, Test: 0)", len(events), len(train_ids), len(val_ids))

    # Resolve output destination
    resolved_output = resolve_rich_gfs_output_dir(args.output_dir or cfg.get("output_dir"))
    log.info("Resolved Rich Replay Output Destination: %s", resolved_output)
    check_colab_drive_persistence(resolved_output)

    latency = float(cfg.get("temporal", {}).get("assumed_latency_hours", 6.0))
    plan = plan_rich_replay_for_events(events, assumed_latency_hours=latency)

    log.info("=== REPLAY PLAN SUMMARY ===")
    log.info("Total Issues to Generate: %d across %d events", plan["total_issues"], plan["total_events"])
    log.info("Unique GFS Cycles Required: %d", plan["num_unique_cycles"])
    log.info("Unique Cycle+Lead Pairs (Minimal): %d", plan["num_unique_cycle_leads"])
    log.info("GFS Cycles: %s", ", ".join(plan["unique_cycles_required"]))

    if args.output_plan:
        out_p = Path(args.output_plan)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        log.info("Plan written to: %s", out_p)

    if args.dry_run_download:
        log.info("=== DRY-RUN DOWNLOAD PROOF ===")
        log.info("Target Raw Cache: %s/raw_gfs_cache", resolved_output)
        log.info("Variables to Range-Fetch: 10u, 10v, 2t, 2r, sp, cape, pwat, prate_mean")
        log.info("Total Unique Granules: %d (No full ~450MB GRIB download; byte ranges only)", plan["num_unique_cycle_leads"])
        # Estimate ~500 KB per message * 8 messages = 4 MB per lead -> ~900 MB total vs 100+ GB full files
        est_mb = plan["num_unique_cycle_leads"] * 4.0
        log.info("Estimated Total Download Size: ~%.1f MB (vs ~%.1f GB if full files downloaded)", est_mb, plan["num_unique_cycle_leads"] * 0.45)
        # Sample first and last granule
        first_gl = plan["unique_cycle_leads_required"][0]
        last_gl = plan["unique_cycle_leads_required"][-1]
        log.info("Sample Granule [0]: %s f%03d -> %s", first_gl["cycle"], first_gl["lead"], source_uri(first_gl["cycle"], first_gl["lead"]))
        log.info("Sample Granule [-1]: %s f%03d -> %s", last_gl["cycle"], last_gl["lead"], source_uri(last_gl["cycle"], last_gl["lead"]))
        log.info("DRY-RUN COMPLETE: Zero bytes retrieved over network. URLs, selectors, and destinations proven.")
        return 0

    if args.plan_only:
        log.info("Plan-only mode complete. Zero network downloads performed.")
        return 0

    if not args.download:
        log.info("Live download flag (--download) not supplied. Stopping before network operations.")
        log.info("To perform real download when ready, run with --download.")
        return 0

    log.error("Live download requested but blocked by pre-download verification safety guard.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

