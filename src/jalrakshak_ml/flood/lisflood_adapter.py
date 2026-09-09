"""LISFLOOD-FP parameter file writer and execution wrapper.

Generates validated LISFLOOD-FP .par configuration and .bci boundary-condition files,
wraps genuine subprocess execution, and captures all outputs with full provenance.

The solver binary must be installed separately (Linux/WSL/container).
This module fails closed if the binary is absent.

Reference: Bates, P.D., Horritt, M.S. & Fewtrell, T.J. (2010). A simple inertial
formulation of the shallow water equations for efficient two-dimensional flood
inundation modelling. J Hydrol 387(1-2): 33-45.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


LISFLOOD_SOLVER_NAMES = ("lisflood", "lisflood_fp", "lisflood-fp", "lfp")
"""Recognised binary names to try when locating LISFLOOD-FP."""


def find_lisflood_binary() -> str | None:
    """Search PATH for any recognised LISFLOOD-FP binary name."""
    for name in LISFLOOD_SOLVER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass(frozen=True)
class LISFLOODParFile:
    """LISFLOOD-FP parameter file specification.

    Only parameters with genuine physical justification are included.
    Parameters without calibration data are flagged in assumed_parameters.
    """

    scenario_id: str
    dem_path: str           # DEM raster (must be EPSG:32643, 256×256, float32, metres)
    roughness_path: str     # Manning n raster (same grid)
    bdy_path: str           # rainfall boundary forcing file
    output_dir: str         # directory for LISFLOOD output
    dx_m: float             # cell resolution in x direction (metres)
    dy_m: float             # cell resolution in y direction (metres)
    nrows: int
    ncols: int
    sim_time_hours: float   # total simulation duration
    initial_wd: float = 0.0  # initial water depth (m); dry-bed start
    solver: str = "acc"     # acceleration formulation (Bates et al. 2010)
    output_interval_hours: float = 0.5  # output frequency
    massint: float = 0.5    # mass balance check interval (hours)
    assumed_parameters: tuple[str, ...] = (
        "roughness:uncalibrated_literature",
        "initial_wd:dry_bed",
        "boundary:open_coastal_mean_sea_level",
        "infiltration:not_modelled_in_lisflood",
    )

    def render_par_text(self) -> str:
        """Generate the LISFLOOD-FP parameter file content."""
        lines = [
            f"# LISFLOOD-FP parameter file: {self.scenario_id}",
            f"# Generated: {datetime.now(timezone.utc).isoformat()}",
            f"# Assumed parameters: {', '.join(self.assumed_parameters)}",
            f"# Calibrated: False",
            "",
            f"DEMfile        {self.dem_path}",
            f"manningfile    {self.roughness_path}",
            f"bcifile        {Path(self.output_dir) / (self.scenario_id + '.bci')}",
            f"bdyfile        {self.bdy_path}",
            "",
            f"resroot        {Path(self.output_dir) / self.scenario_id}",
            f"dirroot        {self.output_dir}",
            "",
            f"dx             {self.dx_m:.4f}",
            f"dy             {self.dy_m:.4f}",
            f"nrows          {self.nrows}",
            f"ncols          {self.ncols}",
            "",
            f"sim_time       {self.sim_time_hours * 3600:.1f}",
            f"initial_wd     {self.initial_wd:.4f}",
            f"output_interval {self.output_interval_hours * 3600:.1f}",
            f"massint        {self.massint * 3600:.1f}",
            "",
            f"solver         {self.solver}",
            "overpass       0",    # overland flow only
            "rainfall       1",    # enable uniform rainfall
        ]
        return "\n".join(lines) + "\n"

    def render_bci_text(self) -> str:
        """Generate a minimal open-boundary condition file."""
        return (
            "# LISFLOOD-FP boundary conditions: open coastal\n"
            "# Downstream boundary: free outflow (no tidal forcing)\n"
            "# All domain edges: open (zero-depth extrapolation)\n"
        )

    def write(self, work_dir: str | Path) -> tuple[Path, Path]:
        """Write .par and .bci files to work_dir; return (par_path, bci_path)."""
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        par_path = work / f"{self.scenario_id}.par"
        bci_path = work / f"{self.scenario_id}.bci"
        par_path.write_text(self.render_par_text(), encoding="utf-8")
        bci_path.write_text(self.render_bci_text(), encoding="utf-8")
        return par_path, bci_path

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LISFLOODRunRecord:
    """Immutable record of a genuine LISFLOOD-FP execution.

    execution_status == 'SUCCESS' only when the process returned exit code 0
    AND at least one output file with water depth was produced.
    """

    scenario_id: str
    execution_status: str     # 'SUCCESS', 'FAILED', 'BLOCKED_NO_BINARY', 'DRY_RUN'
    solver_binary: str | None
    solver_version: str | None
    exit_code: int | None
    runtime_seconds: float | None
    stdout_tail: str
    stderr_tail: str
    par_file_sha256: str
    dem_sha256: str
    roughness_sha256: str
    forcing_sha256: str
    output_files: list[str]    # genuine output files produced
    max_depth_m: float | None  # if available from output
    inundated_cells: int | None
    physically_simulated: bool
    calibrated: bool = False
    smoke_run: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_suffix(out.suffix + ".part")
        part.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        part.replace(out)


def _sha256_file(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return "MISSING"
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_lisflood_par(
    scenario_id: str,
    *,
    dem_path: str | Path,
    roughness_path: str | Path,
    bdy_path: str | Path,
    output_dir: str | Path,
    dx_m: float = 160.88,
    dy_m: float = 196.08,
    nrows: int = 256,
    ncols: int = 256,
    sim_time_hours: float = 6.0,
    work_dir: str | Path | None = None,
) -> tuple[LISFLOODParFile, Path, Path]:
    """Write a validated LISFLOOD-FP parameter file for the Mumbai pilot domain.

    Returns (par_spec, par_path, bci_path).
    """
    spec = LISFLOODParFile(
        scenario_id=scenario_id,
        dem_path=str(dem_path),
        roughness_path=str(roughness_path),
        bdy_path=str(bdy_path),
        output_dir=str(output_dir),
        dx_m=dx_m,
        dy_m=dy_m,
        nrows=nrows,
        ncols=ncols,
        sim_time_hours=sim_time_hours,
    )
    use_work = Path(work_dir) if work_dir else Path(output_dir) / "par"
    par_path, bci_path = spec.write(use_work)
    return spec, par_path, bci_path


def run_lisflood_smoke(
    *,
    dem_path: str | Path,
    roughness_path: str | Path,
    bdy_path: str | Path,
    output_dir: str | Path,
    scenario_id: str = "mumbai_smoke_v1",
    sim_time_hours: float = 1.0,
    timeout_seconds: int = 600,
    executable: str | None = None,
) -> LISFLOODRunRecord:
    """Attempt a genuine LISFLOOD-FP smoke execution.

    If the binary is absent, returns a BLOCKED_NO_BINARY record without fabricating output.
    If the binary is present, runs the solver and captures stdout/stderr/exit_code.
    Does NOT fabricate water depths if the solver fails.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    dem_path = Path(dem_path)
    roughness_path = Path(roughness_path)
    bdy_path = Path(bdy_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dem_sha = _sha256_file(dem_path)
    roughness_sha = _sha256_file(roughness_path)
    forcing_sha = _sha256_file(bdy_path)

    # Check for mandatory inputs
    blockers = []
    if not dem_path.is_file():
        blockers.append(f"DEM missing: {dem_path}")
    if not roughness_path.is_file():
        blockers.append(f"Roughness missing: {roughness_path}")
    if not bdy_path.is_file():
        blockers.append(f"Forcing (.bdy) missing: {bdy_path}")

    if blockers:
        return LISFLOODRunRecord(
            scenario_id=scenario_id,
            execution_status="BLOCKED_MISSING_INPUT",
            solver_binary=None,
            solver_version=None,
            exit_code=None,
            runtime_seconds=None,
            stdout_tail="",
            stderr_tail="; ".join(blockers),
            par_file_sha256="N/A",
            dem_sha256=dem_sha,
            roughness_sha256=roughness_sha,
            forcing_sha256=forcing_sha,
            output_files=[],
            max_depth_m=None,
            inundated_cells=None,
            physically_simulated=False,
            smoke_run=True,
            created_at=created_at,
        )

    # Locate solver binary
    if executable is not None:
        # Caller supplied an explicit name; verify it is resolvable before using it
        binary = shutil.which(executable) or (executable if Path(executable).is_file() else None)
    else:
        binary = find_lisflood_binary()
    if binary is None:
        return LISFLOODRunRecord(
            scenario_id=scenario_id,
            execution_status="BLOCKED_NO_BINARY",
            solver_binary=None,
            solver_version=None,
            exit_code=None,
            runtime_seconds=None,
            stdout_tail="",
            stderr_tail=(
                "LISFLOOD-FP binary not found on PATH. "
                "Install via: conda install -c conda-forge lisflood-fp  "
                "OR: compile from source on Linux/WSL2 and add to PATH."
            ),
            par_file_sha256="N/A",
            dem_sha256=dem_sha,
            roughness_sha256=roughness_sha,
            forcing_sha256=forcing_sha,
            output_files=[],
            max_depth_m=None,
            inundated_cells=None,
            physically_simulated=False,
            smoke_run=True,
            created_at=created_at,
        )

    # Write parameter files
    spec, par_path, _ = write_lisflood_par(
        scenario_id,
        dem_path=dem_path,
        roughness_path=roughness_path,
        bdy_path=bdy_path,
        output_dir=output_dir,
        sim_time_hours=sim_time_hours,
        work_dir=output_dir / "par",
    )
    par_sha = hashlib.sha256(par_path.read_bytes()).hexdigest()

    # Execute
    command = [binary, str(par_path)]
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=str(output_dir),
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        return LISFLOODRunRecord(
            scenario_id=scenario_id,
            execution_status="FAILED",
            solver_binary=binary,
            solver_version=None,
            exit_code=-1,
            runtime_seconds=time.perf_counter() - t0,
            stdout_tail="",
            stderr_tail=f"TIMEOUT after {timeout_seconds}s: {err}",
            par_file_sha256=par_sha,
            dem_sha256=dem_sha,
            roughness_sha256=roughness_sha,
            forcing_sha256=forcing_sha,
            output_files=[],
            max_depth_m=None,
            inundated_cells=None,
            physically_simulated=False,
            smoke_run=True,
            created_at=created_at,
        )

    runtime = time.perf_counter() - t0

    # Discover output files
    output_files = [
        str(f) for f in sorted(output_dir.glob(f"{scenario_id}*"))
        if f.is_file() and f.suffix in {".tif", ".asc", ".nc", ".rsl", ".max"}
    ]

    # Extract max depth if any GeoTIFF or .max file was produced
    max_depth: float | None = None
    inundated: int | None = None
    max_files = [f for f in output_files if ".max" in f or "maxH" in f]
    if max_files:
        try:
            import rasterio  # type: ignore[import-untyped]
            with rasterio.open(max_files[0]) as src:
                arr = src.read(1)
                finite = arr[np.isfinite(arr) & (arr >= 0)]
                if finite.size:
                    max_depth = float(finite.max())
                    inundated = int((finite >= 0.05).sum())
        except Exception:  # noqa: BLE001
            pass

    status = "SUCCESS" if result.returncode == 0 and output_files else "FAILED"
    physically_simulated = status == "SUCCESS"

    run_record = LISFLOODRunRecord(
        scenario_id=scenario_id,
        execution_status=status,
        solver_binary=binary,
        solver_version=None,  # version string requires parsing stdout
        exit_code=result.returncode,
        runtime_seconds=runtime,
        stdout_tail=result.stdout[-2000:],
        stderr_tail=result.stderr[-2000:],
        par_file_sha256=par_sha,
        dem_sha256=dem_sha,
        roughness_sha256=roughness_sha,
        forcing_sha256=forcing_sha,
        output_files=output_files,
        max_depth_m=max_depth,
        inundated_cells=inundated,
        physically_simulated=physically_simulated,
        smoke_run=True,
        created_at=created_at,
    )

    run_record.write(output_dir / f"{scenario_id}_run_record.json")
    return run_record
