"""Physical rainfall scenario generator and batch execution orchestrator.

Workstream 5:
- Generates 6-10 deterministic physical rainfall scenarios covering defensible
  variations in intensity, duration, and temporal profiles.
- Explicitly labelled: source_type = "generated_physics_scenario", synthetic = True.
  NEVER claimed as observed GPM or historical truth.
- Executes scenarios through genuine LISFLOOD-FP solver.
- Records all runs (status, runtime, stdout/stderr, depth raster, hashes).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from jalrakshak_ml.flood.lisflood_adapter import (
    LISFLOODRunRecord,
    find_lisflood_binary,
    run_lisflood_smoke,
)


@dataclass(frozen=True)
class PhysicalRainfallScenario:
    """Deterministic physical rainfall scenario specification."""

    scenario_id: str
    description: str
    duration_hours: float
    cadence_minutes: int
    rates_mm_h: tuple[float, ...]
    peak_rate_mm_h: float
    mean_rate_mm_h: float
    profile_type: str
    source_type: str = "generated_physics_scenario"
    synthetic: bool = True
    observed: bool = False
    calibrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rates_mm_h"] = list(self.rates_mm_h)
        d["rates_sha256"] = hashlib.sha256(
            np.array(self.rates_mm_h, dtype=np.float64).tobytes()
        ).hexdigest()
        return d

    def write_forcing(self, out_dir: str | Path) -> tuple[Path, Path]:
        """Write .rain forcing file and JSON sidecar manifest."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rain_file = out / f"{self.scenario_id}.rain"
        meta_file = out / f"{self.scenario_id}.json"

        from .forecast_to_forcing import write_interval_rain
        if self.cadence_minutes != 30 or not np.isclose(len(self.rates_mm_h) / 2, self.duration_hours):
            raise ValueError('Scenario intervals must cover duration at 30-minute cadence')
        encoding = write_interval_rain(rain_file, np.asarray(self.rates_mm_h))
        meta_file.write_text(json.dumps({**self.to_dict(), **encoding}, indent=2), encoding="utf-8")
        return rain_file, meta_file


def get_default_scenario_batch(count: int = 8) -> list[PhysicalRainfallScenario]:
    """Return a deterministic corpus of defensible physical rainfall scenarios.

    Covers intensity variations (15-110 mm/h), durations (1.0-1.5h), and temporal shapes
    (steady, front-loaded, back-loaded, symmetric pulse, cloudburst).
    """
    catalog = [
        PhysicalRainfallScenario(
            scenario_id="scenario_01_low_steady",
            description="Low-intensity uniform rainfall across pilot domain",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(15.0, 15.0),
            peak_rate_mm_h=15.0,
            mean_rate_mm_h=15.0,
            profile_type="steady",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_02_mod_steady",
            description="Moderate monsoon downpour uniform across pilot domain",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(35.0, 35.0),
            peak_rate_mm_h=35.0,
            mean_rate_mm_h=35.0,
            profile_type="steady",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_03_high_steady",
            description="Heavy monsoon rainfall uniform across pilot domain",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(60.0, 60.0),
            peak_rate_mm_h=60.0,
            mean_rate_mm_h=60.0,
            profile_type="steady",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_04_front_loaded",
            description="Front-loaded convective cloudburst decaying to light rain",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(80.0, 20.0),
            peak_rate_mm_h=80.0,
            mean_rate_mm_h=50.0,
            profile_type="front_loaded",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_05_back_loaded",
            description="Gradually intensifying rainfall peaking at storm end",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(20.0, 80.0),
            peak_rate_mm_h=80.0,
            mean_rate_mm_h=50.0,
            profile_type="back_loaded",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_06_short_intense",
            description="Short 1-hour intense storm cell",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(90.0, 45.0),
            peak_rate_mm_h=90.0,
            mean_rate_mm_h=67.5,
            profile_type="short_intense",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_07_mod_pulse",
            description="Symmetric rainfall pulse with central peak",
            duration_hours=1.5,
            cadence_minutes=30,
            rates_mm_h=(20.0, 65.0, 20.0),
            peak_rate_mm_h=65.0,
            mean_rate_mm_h=35.0,
            profile_type="pulse",
        ),
        PhysicalRainfallScenario(
            scenario_id="scenario_08_flash_burst",
            description="Severe cloudburst burst peaking at 110 mm/h",
            duration_hours=1.0,
            cadence_minutes=30,
            rates_mm_h=(110.0, 25.0),
            peak_rate_mm_h=110.0,
            mean_rate_mm_h=67.5,
            profile_type="cloudburst",
        ),
    ]
    return catalog[:count]


def execute_scenario_batch(
    scenarios: list[PhysicalRainfallScenario],
    *,
    dem_path: str | Path,
    roughness_path: str | Path = "data/processed/static/roughness.tif",
    output_root: str | Path,
    solver_binary: str | None = None,
    timeout_per_run: int = 600,
) -> dict[str, Any]:
    """Execute a batch of scenarios through genuine LISFLOOD-FP solver.

    Records each run individually, collects outputs, and builds a batch manifest.
    """
    out_root = Path(output_root)
    out_root.mkdir(parents=True, exist_ok=True)
    forcing_dir = out_root / "forcing"
    runs_dir = out_root / "runs"
    forcing_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    binary = solver_binary or find_lisflood_binary()
    batch_records: list[dict[str, Any]] = []
    t_start = time.time()

    print(f"\n=== EXECUTING SCENARIO BATCH: {len(scenarios)} SCENARIOS ===")
    print(f"Solver: {binary}")

    for idx, sc in enumerate(scenarios, 1):
        print(f"\n[{idx}/{len(scenarios)}] Running {sc.scenario_id} ({sc.profile_type}, peak={sc.peak_rate_mm_h} mm/h)...")
        # Write forcing
        rain_file, _ = sc.write_forcing(forcing_dir)
        sc_run_dir = runs_dir / sc.scenario_id

        # Execute
        rec = run_lisflood_smoke(
            dem_path=dem_path,
            roughness_path=roughness_path,
            bdy_path=rain_file,
            output_dir=sc_run_dir,
            scenario_id=sc.scenario_id,
            sim_time_hours=sc.duration_hours,
            timeout_seconds=timeout_per_run,
            executable=binary,
        )
        rec_dict = rec.to_dict()
        rec_dict["scenario_metadata"] = {
            "rainfall_rate_mm_h": sc.peak_rate_mm_h,
            "mean_rate_mm_h": sc.mean_rate_mm_h,
            "pattern": sc.profile_type,
            "duration_hours": sc.duration_hours,
        }
        batch_records.append(rec_dict)

        if rec.execution_status == "SUCCESS":
            print(f"  [OK] Status=SUCCESS, runtime={rec.runtime_seconds:.1f}s, "
                  f"max_depth={rec.max_depth_m:.3f}m, wet_cells={rec.inundated_cells}")
        else:
            print(f"  [FAIL] Status={rec.execution_status}, error: {rec.stderr_tail[:200]}")

    total_time = time.time() - t_start
    success_count = sum(1 for r in batch_records if r["execution_status"] == "SUCCESS")
    failed_count = len(batch_records) - success_count

    depths = [r["max_depth_m"] for r in batch_records if r.get("max_depth_m") is not None]
    peak_depth = max(depths) if depths else 0.0
    total_wet = sum(r.get("inundated_cells") or 0 for r in batch_records)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "n_scenarios": len(scenarios),
        "successful_runs": success_count,
        "n_succeeded": success_count,
        "failed_runs": failed_count,
        "total_elapsed_seconds": round(total_time, 2),
        "peak_depth_m": peak_depth,
        "total_wet_cells_generated": total_wet,
        "solver_binary": binary,
        "runs": batch_records,
    }

    manifest_path = out_root / "batch_execution_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nBatch complete: {success_count}/{len(scenarios)} successful ({total_time:.1f}s total)")
    return manifest
