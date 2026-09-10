"""LISFLOOD-FP parameter file writer and execution wrapper.

Generates validated LISFLOOD-FP .par configuration and .bci boundary-condition files,
wraps genuine subprocess execution (native Linux/Windows or WSL2), and captures all
outputs with full provenance.

The solver binary must be installed separately (Linux/WSL/container).
This module fails closed if the binary is absent.

Reference: Bates, P.D., Horritt, M.S. & Fewtrell, T.J. (2010). A simple inertial
formulation of the shallow water equations for efficient two-dimensional flood
inundation modelling. J Hydrol 387(1-2): 33-45.
"""

from __future__ import annotations

import hashlib
import json
import platform
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
    """Search PATH and WSL2 environment for any recognised LISFLOOD-FP binary name."""
    # 1. Search native PATH
    for name in LISFLOOD_SOLVER_NAMES:
        found = shutil.which(name)
        if found:
            return found

    # 2. Check cached manifest
    manifest_path = Path("reports/lisflood_installation_manifest.json")
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            bin_path = data.get("binary_path")
            if bin_path:
                return bin_path
        except Exception:
            pass

    # 3. On Windows, check WSL2
    if platform.system() == "Windows" and shutil.which("wsl"):
        try:
            cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-c", "which lisflood 2>/dev/null || true"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            wsl_path = proc.stdout.strip()
            if wsl_path and "/lisflood" in wsl_path:
                return f"wsl:{wsl_path}"
        except Exception:
            pass

    return None


def to_wsl_path(path: str | Path) -> str:
    """Convert a Windows Path to a WSL /mnt/... posix path."""
    p = Path(path).resolve()
    posix = p.as_posix()
    if p.drive:
        drive_letter = p.drive[0].lower()
        return f"/mnt/{drive_letter}" + posix[len(p.drive):]
    return posix


def ensure_ascii_dem(
    dem_path: str | Path,
    output_dir: str | Path,
    target_name: str = "mumbai_dem.asc",
) -> Path:
    """Ensure the DEM is formatted as an ESRI ASCII raster grid (.asc) for LISFLOOD-FP."""
    p = Path(dem_path)
    import rasterio
    with rasterio.open(p) as source:
        t = source.transform
        if t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0 or not np.isclose(t.a, -t.e):
            raise ValueError('LISFLOOD ASCII requires a north-up square grid; explicitly reproject first')
        if source.crs is None or not source.crs.is_projected:
            raise ValueError('Projected metre CRS required')
    if p.suffix.lower() in (".asc", ".dem"):
        return p

    out_asc = Path(output_dir) / target_name
    if out_asc.is_file() and out_asc.stat().st_size > 1000:
        return out_asc

    out_asc.parent.mkdir(parents=True, exist_ok=True)
    try:
        import rasterio

        with rasterio.open(p) as src:
            arr = src.read(1).astype(np.float64)
            transform = src.transform
            nrows, ncols = arr.shape
            xll = transform.c
            yll = transform.f + (nrows * transform.e)
            cellsize = abs(transform.a)
            nodata = -9999.0

            arr_clean = np.where(np.isnan(arr) | (arr <= -9000.0), nodata, arr)

            with open(out_asc, "w", encoding="utf-8") as f:
                f.write(f"ncols         {ncols}\n")
                f.write(f"nrows         {nrows}\n")
                f.write(f"xllcorner     {xll:.4f}\n")
                f.write(f"yllcorner     {yll:.4f}\n")
                f.write(f"cellsize      {cellsize:.4f}\n")
                f.write(f"NODATA_value  {nodata:.1f}\n")
                for row in arr_clean:
                    f.write(" ".join(f"{v:.2f}" for v in row) + "\n")
    except Exception as exc:
        raise ValueError('Cannot create solver DEM from invalid source') from exc

    return out_asc


def ensure_lisflood_rain(
    forcing_path: str | Path,
    output_dir: str | Path,
    target_name: str = "rainfall.rain",
    *,
    column_order: str | None = None,
) -> Path:
    """Format explicit .rain rate/time or repository .bdy time/rate contracts."""
    from .forensic import read_rain
    in_file = Path(forcing_path)
    out_file = Path(output_dir) / target_name
    out_file.parent.mkdir(parents=True, exist_ok=True)

    order = column_order or {'.rain': 'rate_time', '.bdy': 'time_rate'}.get(in_file.suffix)
    rates, times, unit = read_rain(in_file, column_order=order)
    times = times / (3600 if unit == 'hours' else 1)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# LISFLOOD-FP rainfall input\n")
        f.write(f"{len(rates)} {unit}\n")
        for rate, timestamp in zip(rates, times, strict=True):
            f.write(f"{rate:.4f}\t{timestamp:.10f}\n")

    return out_file


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
            f"saveint        {self.output_interval_hours * 3600:.1f}",
            f"massint        {self.massint * 3600:.1f}",
            "",
            f"solver         {self.solver}",
            "overpass       0",    # overland flow only
            "rainfall       1",    # enable uniform rainfall
            "acceleration",
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
    execution_status: str     # 'SUCCESS', 'FAILED', 'BLOCKED_NO_BINARY', 'BLOCKED_MISSING_INPUT', 'DRY_RUN'
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
    mean_wet_depth_m: float | None = None
    depth_raster_path: str | None = None
    command: list[str] | None = None
    work_directory: str | None = None
    consumed_forcing_sha256: str | None = None
    consumed_dem_sha256: str | None = None

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
    If the binary is present (native or via WSL2), runs the solver and captures stdout/stderr/exit_code.
    Does NOT fabricate water depths if the solver fails.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    dem_path = Path(dem_path)
    roughness_path = Path(roughness_path)
    bdy_path = Path(bdy_path)
    output_dir = Path(output_dir)
    if (output_dir / 'results').is_dir() and any((output_dir / 'results').iterdir()):
        raise FileExistsError('Solver output version already contains results; choose a new run directory')
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
        if executable.startswith("wsl:"):
            binary = executable
        else:
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
                "LISFLOOD-FP binary not found on PATH or WSL2. "
                "Run: python scripts/bootstrap_lisflood.py to install."
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

    # Setup solver workspace
    work_dir = output_dir / "work"
    results_dir = output_dir / "results"
    work_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # Prepare ESRI ASCII DEM and rainfall forcing
    asc_dem = ensure_ascii_dem(dem_path, work_dir, "mumbai_dem.asc")
    rain_forcing = ensure_lisflood_rain(bdy_path, work_dir, "mumbai_rain.rain")
    from .forensic import read_rain
    _, rain_times, _ = read_rain(rain_forcing)
    if rain_times[0] != 0 or rain_times[-1] < sim_time_hours * 3600:
        raise ValueError('Forcing must cover the complete simulation period from time zero')

    is_wsl = binary.startswith("wsl:")
    wsl_bin = binary[4:] if is_wsl else binary

    # Write LISFLOOD 8.0 par file
    par_path = work_dir / f"{scenario_id}.par"
    par_content = [
        f"# LISFLOOD-FP parameter file: {scenario_id}",
        f"DEMfile\t{asc_dem.name}",
        "fpfric\t0.04",
        f"rainfall\t{rain_forcing.name}",
        f"resroot\t{scenario_id}",
        "dirroot\tresults",
        f"sim_time\t{int(sim_time_hours * 3600)}",
        "initial_tstep\t5",
        f"massint\t{min(1800, int(sim_time_hours * 1800))}",
        f"saveint\t{min(1800, int(sim_time_hours * 1800))}",
        "acceleration",
    ]
    par_path.write_text("\n".join(par_content) + "\n", encoding="utf-8")
    par_sha = hashlib.sha256(par_path.read_bytes()).hexdigest()

    # Create symlink or copy of results dir inside work_dir so dirroot 'results' works
    (work_dir / "results").mkdir(exist_ok=True)

    # Execute solver
    t0 = time.perf_counter()
    try:
        if is_wsl:
            wsl_work_dir = to_wsl_path(work_dir)
            wsl_cmd = f"cd '{wsl_work_dir}' && {wsl_bin} '{par_path.name}'"
            cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-c", wsl_cmd]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        else:
            cmd = [wsl_bin, par_path.name]
            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
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

    # Discover genuine output files in work_dir/results and move/copy them to results_dir
    raw_files = sorted((work_dir / "results").glob(f"{scenario_id}*"))
    output_files = []
    for f in raw_files:
        dest = results_dir / f.name
        if f != dest:
            shutil.copy2(f, dest)
        output_files.append(str(dest))

    # Parse max depth from ESRI ASCII .max raster
    max_depth: float | None = None
    inundated: int | None = None
    mean_wet_depth: float | None = None
    depth_tif_path: str | None = None

    max_asc = results_dir / f"{scenario_id}.max"
    if max_asc.is_file():
        try:
            from .forensic import read_ascii
            depth_arr, output_transform, output_nodata = read_ascii(max_asc)
            valid = depth_arr != output_nodata
            if not valid.any() or not np.isfinite(depth_arr[valid]).all() or (depth_arr[valid] < 0).any():
                raise ValueError('Invalid solver depth; no clipping or manufactured targets')
            finite = depth_arr[valid]
            if finite.size:
                max_depth = float(finite.max())
                wet = finite[finite >= 0.05]
                inundated = int(wet.size)
                mean_wet_depth = float(wet.mean()) if wet.size else 0.0

            # Export genuine simulated water depth GeoTIFF with domain spatial metadata
            import rasterio
            with rasterio.open(dem_path) as dem_src:
                if depth_arr.shape != dem_src.shape or not np.allclose(
                    tuple(dem_src.transform)[:6], tuple(output_transform)[:6], atol=.02, rtol=0
                ):
                    raise ValueError('Solver output grid differs from DEM; explicit reprojection required')
                meta = dem_src.meta.copy()
                meta.update(dtype=rasterio.float32, count=1, nodata=-9999.0)

            depth_tif = results_dir / f"{scenario_id}_simulated_depth.tif"
            with rasterio.open(depth_tif, "w", **meta) as dst:
                dst.write(np.where(depth_arr < 0, -9999.0, depth_arr).astype(np.float32), 1)

            output_files.append(str(depth_tif))
            depth_tif_path = str(depth_tif)
        except Exception as err:
            max_depth = None
            inundated = None
            result.stderr += f"\n[Depth parse error: {err}]"

    # Extract version banner from stdout
    solver_version = None
    for line in result.stdout.splitlines():
        if "LISFLOOD-FP version" in line:
            solver_version = line.strip()
            break

    status = "SUCCESS" if result.returncode == 0 and output_files and max_depth is not None else "FAILED"
    physically_simulated = status == "SUCCESS"

    run_record = LISFLOODRunRecord(
        scenario_id=scenario_id,
        execution_status=status,
        solver_binary=binary,
        solver_version=solver_version,
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
        mean_wet_depth_m=mean_wet_depth,
        depth_raster_path=depth_tif_path,
        physically_simulated=physically_simulated,
        smoke_run=True,
        created_at=created_at,
        command=cmd,
        work_directory=str(work_dir.resolve()),
        consumed_forcing_sha256=_sha256_file(rain_forcing),
        consumed_dem_sha256=_sha256_file(asc_dem),
    )

    run_record.write(output_dir / f"{scenario_id}_run_record.json")
    return run_record
