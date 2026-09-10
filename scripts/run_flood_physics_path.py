"""Workstream D + F + H: Mumbai flood-physics execution path and FNO readiness.

Entry point that:
1. Prepares and validates the Mumbai pilot domain
2. Repairs DEM NaN cells (nearest-neighbor, no interpolation)
3. Attempts LISFLOOD-FP smoke execution (fail-closed if binary absent)
4. Validates existing rainfall forcing
5. Runs full FNO readiness audit
6. Generates the LISFLOOD .par parameter file for future execution
7. Writes an execution-status JSON report

Nothing is fabricated. All blockers are recorded explicitly.
Phase 4E training data is NOT accessed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mumbai flood-physics execution path — Workstream D+F+H"
    )
    parser.add_argument(
        "--dem", default="data/processed/static/elevation.tif",
        help="DEM raster path"
    )
    parser.add_argument(
        "--roughness", default="data/processed/static/roughness.tif",
        help="Manning roughness raster path"
    )
    parser.add_argument(
        "--bdy", default="data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.bdy",
        help="Rainfall forcing .bdy file"
    )
    parser.add_argument(
        "--output-dir", default="data/processed/flood/physics_outputs",
        help="Directory for physics run outputs"
    )
    parser.add_argument(
        "--report-dir", default="reports",
        help="Directory for final reports"
    )
    parser.add_argument(
        "--sim-time-hours", type=float, default=1.0,
        help="Smoke run duration (hours)"
    )
    parser.add_argument(
        "--lisflood-exe", default=None,
        help="Override LISFLOOD-FP binary path"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Prepare domain and report without running solver"
    )
    args = parser.parse_args(argv)

    report: dict = {
        "script": "run_flood_physics_path.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sections": {},
    }

    output_dir = Path(args.output_dir)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Domain preparation ────────────────────────────────────────────────
    print("\n[1/5] Preparing Mumbai pilot domain...")
    try:
        from jalrakshak_ml.flood.domain import prepare_mumbai_domain
        domain = prepare_mumbai_domain(
            dem_path=args.dem,
            roughness_path=args.roughness,
            output_path="data/processed/flood/domain/mumbai_pilot_domain.json",
        )
        report["sections"]["domain"] = {
            "status": "OK",
            "domain_id": domain.domain_id,
            "crs": domain.crs,
            "grid_shape": list(domain.grid_shape),
            "resolution_m": domain.pixel_resolution_m,
            "dem_nan_cells": domain.dem_nan_cells,
            "dem_repaired": domain.dem_repaired,
            "dem_repair_method": domain.dem_repair_method,
            "roughness_calibrated": domain.roughness_calibrated,
            "blockers": list(domain.blockers),
        }
        print(f"  Domain: {domain.grid_shape} @ {domain.pixel_resolution_m:.1f}m  CRS={domain.crs}")
        print(f"  DEM NaN cells: {domain.dem_nan_cells}  Repaired: {domain.dem_repaired}")
        if domain.blockers:
            print(f"  BLOCKERS: {domain.blockers}")
    except Exception as e:  # noqa: BLE001
        report["sections"]["domain"] = {"status": "ERROR", "error": str(e)}
        print(f"  ERROR: {e}")

    # ── 2. Rainfall forcing validation ──────────────────────────────────────
    print("\n[2/5] Validating rainfall forcing...")
    try:
        from jalrakshak_ml.flood.gpm_to_forcing import build_forcing_from_existing_bdy
        forcing_meta = build_forcing_from_existing_bdy(args.bdy)
        report["sections"]["forcing"] = {"status": "OK", **forcing_meta}
        print(f"  Forcing: {forcing_meta.get('n_timesteps')} steps  "
              f"mean={forcing_meta.get('mean_rate_mm_h', 0):.2f} mm/h  "
              f"max={forcing_meta.get('max_rate_mm_h', 0):.2f} mm/h")
    except FileNotFoundError as e:
        report["sections"]["forcing"] = {"status": "MISSING", "error": str(e)}
        print(f"  MISSING: {e}")
    except Exception as e:  # noqa: BLE001
        report["sections"]["forcing"] = {"status": "ERROR", "error": str(e)}
        print(f"  ERROR: {e}")

    # ── 3. LISFLOOD-FP parameter file preparation ────────────────────────────
    print("\n[3/5] Generating LISFLOOD-FP parameter files...")
    par_written = False
    try:
        from jalrakshak_ml.flood.lisflood_adapter import write_lisflood_par
        dom_data = report["sections"].get("domain", {})
        shape = dom_data.get("grid_shape", [256, 256])
        resolution = dom_data.get("resolution_m", 160.88)

        # Determine effective DEM path (repaired if available)
        dem_path = args.dem
        repaired_dem = Path(args.dem).parent / "elevation_repaired.tif"
        if repaired_dem.is_file():
            dem_path = str(repaired_dem)
            print(f"  Using repaired DEM: {dem_path}")

        spec, par_path, bci_path = write_lisflood_par(
            "mumbai_smoke_v1",
            dem_path=dem_path,
            roughness_path=args.roughness,
            bdy_path=args.bdy,
            output_dir=str(output_dir),
            dx_m=resolution,
            dy_m=resolution,
            nrows=shape[0],
            ncols=shape[1],
            sim_time_hours=args.sim_time_hours,
            work_dir=output_dir / "par",
        )
        par_written = True
        report["sections"]["par_file"] = {
            "status": "WRITTEN",
            "par_path": str(par_path),
            "bci_path": str(bci_path),
            "sim_time_hours": args.sim_time_hours,
            "grid_shape": shape,
            "resolution_m": resolution,
            "assumed_parameters": list(spec.assumed_parameters),
        }
        print(f"  .par written: {par_path}")
        print(f"  .bci written: {bci_path}")
    except Exception as e:  # noqa: BLE001
        report["sections"]["par_file"] = {"status": "ERROR", "error": str(e)}
        print(f"  ERROR: {e}")

    # ── 4. LISFLOOD-FP smoke execution attempt ───────────────────────────────
    print("\n[4/5] Attempting LISFLOOD-FP smoke execution...")
    if args.dry_run:
        print("  --dry-run: skipping solver execution")
        report["sections"]["solver_execution"] = {"status": "DRY_RUN_SKIPPED"}
    else:
        try:
            from jalrakshak_ml.flood.lisflood_adapter import run_lisflood_smoke
            run_record = run_lisflood_smoke(
                dem_path=args.dem,
                roughness_path=args.roughness,
                bdy_path=args.bdy,
                output_dir=str(output_dir),
                scenario_id="mumbai_smoke_v1",
                sim_time_hours=args.sim_time_hours,
                executable=args.lisflood_exe,
            )
            report["sections"]["solver_execution"] = run_record.to_dict()
            status = run_record.execution_status
            if status == "SUCCESS":
                print(f"  [OK] LISFLOOD-FP SUCCESS: {run_record.runtime_seconds:.1f}s  "
                      f"max_depth={run_record.max_depth_m}m  "
                      f"inundated={run_record.inundated_cells} cells")
            elif status == "BLOCKED_NO_BINARY":
                print("  [BLOCKED] LISFLOOD-FP binary not on PATH -- physics execution blocked")
                print("     To install: conda install -c conda-forge lisflood-fp")
                print("     Or compile from source on Linux/WSL2")
            elif status == "BLOCKED_MISSING_INPUT":
                print(f"  [BLOCKED] Missing inputs: {run_record.stderr_tail}")
            else:
                print(f"  [FAILED] (exit {run_record.exit_code}): {run_record.stderr_tail[-400:]}")
        except Exception as e:  # noqa: BLE001
            report["sections"]["solver_execution"] = {"status": "ERROR", "error": str(e)}
            print(f"  ERROR: {e}")

    # ── 5. FNO readiness audit ───────────────────────────────────────────────
    print("\n[5/5] Running FNO readiness audit...")
    try:
        from jalrakshak_ml.flood.fno_readiness import write_fno_readiness_report
        fno_report = write_fno_readiness_report(
            output_path=report_dir / "fno_readiness_audit.json"
        )
        report["sections"]["fno_readiness"] = fno_report.to_dict()
        status = "READY" if fno_report.ready_for_training else "BLOCKED"
        print(f"  FNO status: {status}")
        if fno_report.blockers:
            for b in fno_report.blockers:
                print(f"    BLOCKER: {b}")
        else:
            print("  Architecture [OK]  Loss [OK]  Metrics [OK]  Checkpoint [OK]")
            print(f"  Training blocked until: {fno_report.smoke_train_config.get('blocker_for_training')}")
    except Exception as e:  # noqa: BLE001
        report["sections"]["fno_readiness"] = {"status": "ERROR", "error": str(e)}
        print(f"  ERROR: {e}")

    # ── Summary ──────────────────────────────────────────────────────────────
    exec_status = report["sections"].get("solver_execution", {}).get("execution_status", "UNKNOWN")
    fno_ready = report["sections"].get("fno_readiness", {}).get("ready_for_training", False)
    par_ok = report["sections"].get("par_file", {}).get("status") == "WRITTEN"
    domain_ok = report["sections"].get("domain", {}).get("status") == "OK"
    forcing_ok = report["sections"].get("forcing", {}).get("status") == "OK"

    report["summary"] = {
        "domain_prepared": domain_ok,
        "forcing_validated": forcing_ok,
        "par_file_written": par_ok,
        "solver_execution_status": exec_status,
        "solver_physically_simulated": exec_status == "SUCCESS",
        "fno_ready_for_training": fno_ready,
        "genuine_depth_available": exec_status == "SUCCESS",
        "fabricated_depth": False,
    }

    report_path = report_dir / "flood_physics_execution_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {report_path}")

    # Print concise summary
    print("\n" + "=" * 60)
    print("FLOOD PHYSICS EXECUTION SUMMARY")
    print("=" * 60)
    print(f"  Domain prepared       : {'OK' if domain_ok else 'FAIL'}")
    print(f"  Forcing validated     : {'OK' if forcing_ok else 'FAIL'}")
    print(f"  PAR file written      : {'OK' if par_ok else 'FAIL'}")
    print(f"  Solver execution      : {exec_status}")
    print(f"  Genuine depth avail   : {'YES' if exec_status == 'SUCCESS' else 'NO (binary required)'}")
    print(f"  FNO architecture ready: {'OK' if fno_ready else 'FAIL'}")
    print(f"  Fabricated depth      : NEVER")
    print("=" * 60)

    if exec_status == "BLOCKED_NO_BINARY":
        print("\nNEXT STEP: Install LISFLOOD-FP to obtain genuine water depth targets.")
        print("  conda install -c conda-forge lisflood-fp   # Linux/WSL2 only")
        print("  Then re-run: python scripts/run_flood_physics_path.py")

    return 0 if (domain_ok and forcing_ok and par_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
