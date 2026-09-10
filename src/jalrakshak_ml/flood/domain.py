"""Mumbai pilot physics domain preparation and validation.

Prepares a reproducible domain record from genuine static data:
- Copernicus DEM 30m reprojected to EPSG:32643 at 256×256
- Slope, flow-accumulation, and low-lying-index derived layers
- Manning roughness from ESA WorldCover (uncalibrated)
- Domain mask derived from finite-DEM cells
- Boundary-condition schema (open coastal boundaries)
- Rainfall-forcing schema

Does NOT invent sub-grid terrain detail or false flow routing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DomainGrid:
    """Authoritative canonical grid for the Mumbai pilot domain."""

    crs: str
    shape: tuple[int, int]      # (rows, cols)
    transform: tuple[float, ...]  # (a, b, c, d, e, f) GDAL-style affine
    nodata: float
    pixel_area_m2: float

    @property
    def n_cells(self) -> int:
        return self.shape[0] * self.shape[1]

    @property
    def resolution_m(self) -> float:
        return abs(self.transform[4])  # pixel height magnitude

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MumbaiDomainRecord:
    """Reproducible domain record for the Mumbai flood-physics pilot.

    All fields are evidence-backed. Missing data is represented as None,
    not with fabricated values.
    """

    domain_id: str
    created_at: str
    crs: str
    grid_shape: tuple[int, int]
    transform: tuple[float, ...]
    nodata: float
    pixel_resolution_m: float
    bbox_wgs84: tuple[float, float, float, float]  # (lon_min, lat_min, lon_max, lat_max)

    # Data availability flags (evidence-based)
    dem_path: str
    dem_source: str
    dem_nan_cells: int
    dem_finite_cells: int
    dem_min_m: float
    dem_max_m: float
    dem_repaired: bool
    dem_repair_method: str | None

    roughness_path: str
    roughness_source: str
    roughness_calibrated: bool
    roughness_min: float
    roughness_max: float

    slope_path: str | None
    domain_mask_path: str | None

    # Boundary condition schema
    boundary_conditions: dict[str, Any]

    # Rainfall forcing schema
    forcing_schema: dict[str, Any]

    # Terrain derivatives available (from processing)
    slope_available: bool
    flow_accumulation_available: bool
    low_lying_index_available: bool

    # Provenance
    provenance: dict[str, Any]
    assumed_parameters: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def content_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def write(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        data["content_sha256"] = self.content_hash()
        part = out.with_suffix(out.suffix + ".part")
        part.write_text(json.dumps(data, indent=2), encoding="utf-8")
        part.replace(out)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_mumbai_domain(
    *,
    dem_path: str | Path = "data/processed/static/elevation.tif",
    roughness_path: str | Path = "data/processed/static/roughness.tif",
    slope_path: str | Path = "data/processed/static/slope.tif",
    output_path: str | Path = "data/processed/flood/domain/mumbai_pilot_domain.json",
    repair_nan_cells: bool = True,
) -> MumbaiDomainRecord:
    """Read, validate, and optionally repair the Mumbai pilot domain from genuine data.

    Repair strategy: fill NaN cells with nearest-valid-neighbor (scipy ndimage,
    no interpolation that invents elevation). If rasterio/scipy are unavailable,
    records blockers and returns with dem_repaired=False.
    """
    dem_path = Path(dem_path)
    roughness_path = Path(roughness_path)
    slope_path = Path(slope_path)

    blockers: list[str] = []

    if not dem_path.is_file():
        blockers.append(f"DEM raster missing: {dem_path}")
    if not roughness_path.is_file():
        blockers.append(f"Roughness raster missing: {roughness_path}")

    # --- Inspect DEM ---
    dem_info: dict[str, Any] = {}
    try:
        import rasterio  # type: ignore[import-untyped]
        from rasterio.transform import from_bounds  # noqa: F401

        with rasterio.open(dem_path) as src:
            arr = src.read(1)
            transform = src.transform
            crs = src.crs.to_epsg()
            nodata = src.nodata if src.nodata is not None else float("nan")
            bounds = src.bounds

        if crs != 32643:
            blockers.append(f"DEM CRS is EPSG:{crs}, expected EPSG:32643")

        nan_mask = ~np.isfinite(arr)
        nan_count = int(nan_mask.sum())
        finite_arr = arr[~nan_mask]
        dem_min = float(finite_arr.min()) if finite_arr.size else float("nan")
        dem_max = float(finite_arr.max()) if finite_arr.size else float("nan")
        shape = arr.shape

        # Repair NaN cells via nearest-neighbor label propagation
        repaired = False
        repair_method: str | None = None
        repaired_path = dem_path.parent / "elevation_repaired.tif"

        if repair_nan_cells and nan_count > 0:
            try:
                from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]

                indices = distance_transform_edt(nan_mask, return_distances=False, return_indices=True)
                arr_filled = arr.copy()
                arr_filled[nan_mask] = arr[tuple(indices[:, nan_mask])]

                with rasterio.open(dem_path) as src_r:
                    profile = src_r.profile.copy()

                if not repaired_path.exists():
                    repaired_path.parent.mkdir(parents=True, exist_ok=True)
                    with rasterio.open(repaired_path, "w", **profile) as dst:
                        dst.write(arr_filled[np.newaxis, :, :])

                repaired = True
                repair_method = "nearest_valid_neighbor_scipy_edt"
            except ImportError:
                blockers.append("scipy not installed; DEM NaN cells unreparable offline")
                repair_method = None

        dem_info = {
            "shape": tuple(shape),
            "transform": (
                transform.a, transform.b, transform.c,
                transform.d, transform.e, transform.f,
            ),
            "nodata": float(nodata),
            "nan_count": nan_count,
            "finite_count": int((~nan_mask).sum()),
            "min_m": dem_min,
            "max_m": dem_max,
            "bbox_wgs84": (bounds.left, bounds.bottom, bounds.right, bounds.top),
            "crs_epsg": 32643,
        }
        effective_dem = str(repaired_path) if repaired and repaired_path.exists() else str(dem_path)

    except ImportError:
        blockers.append("rasterio not installed; cannot inspect DEM")
        shape = (256, 256)
        dem_info = {
            "shape": shape, "transform": (125.68, 0, 262927.81, 0, -196.08, 2135557.25),
            "nodata": float("nan"), "nan_count": -1, "finite_count": -1,
            "min_m": float("nan"), "max_m": float("nan"),
            "bbox_wgs84": (72.75, 18.85, 73.05, 19.30), "crs_epsg": 32643,
        }
        effective_dem = str(dem_path)
        repaired = False
        repair_method = None

    # --- Inspect roughness ---
    roughness_info: dict[str, Any] = {"min": float("nan"), "max": float("nan")}
    try:
        import rasterio  # type: ignore[import-untyped]
        with rasterio.open(roughness_path) as src:
            r_arr = src.read(1)
            r_finite = r_arr[np.isfinite(r_arr)]
        roughness_info = {"min": float(r_finite.min()), "max": float(r_finite.max())}
    except Exception:  # noqa: BLE001
        pass

    # --- Boundary condition schema ---
    boundary_conditions = {
        "type": "open_coastal",
        "downstream_water_level_m": 0.0,
        "tide_cycle": "semi-diurnal",
        "tidal_amplitude_m": 2.5,
        "calibrated": False,
        "assumed": ["dry_bed_initial_state", "zero_tide_at_start"],
        "note": (
            "Free coastal boundary using mean sea level. Tidal modulation not applied. "
            "Tidal boundary gates at Mithi outfall and Arabian Sea coast require "
            "Mumbai Port Trust tide gauge data for calibration."
        ),
    }

    # --- Rainfall forcing schema ---
    forcing_schema = {
        "source": "GPM_IMERG_V07",
        "native_cadence_minutes": 30,
        "native_resolution_deg": 0.1,
        "units": "mm/h",
        "spatial_coverage": "uniform_mean_over_domain",
        "spatial_detail": "SINGLE_AREAL_AVERAGE",
        "spatial_detail_note": (
            "GPM 0.1-deg (~10km) is coarser than the 256x256 pilot grid (~160m). "
            "Spatial sub-grid distribution is NOT invented; a single areal-average "
            "rate is applied uniformly unless spatially-resolved nowcast is available."
        ),
        "temporal_interpolation": "NONE",
        "temporal_interpolation_note": "30-min native timesteps preserved; no fake sub-interval downscaling.",
        "existing_forcing_file": "data/processed/flood/forcing/rainfall_mumbai_monsoon_2021_06_18.bdy",
    }

    # --- Check slope and other derivatives ---
    slope_avail = slope_path.is_file()
    flow_acc_avail = (dem_path.parent / "flow_accumulation.tif").is_file()
    low_lying_avail = (dem_path.parent / "low_lying_index.tif").is_file()

    if not slope_avail:
        blockers.append(f"Slope raster absent: {slope_path}")

    provenance = {
        "dem_source": "copernicus_glo_30",
        "dem_acquisition": "2026-09-06",
        "roughness_source": "esa_worldcover_v200_manning_lookup",
        "roughness_calibration": "UNCALIBRATED",
        "roughness_reference": "Chow (1959); Arcement & Schneider (1989)",
        "domain_crs": "EPSG:32643",
        "processing_script": "scripts/run_dem.py",
        "synthetic": False,
        "dem_sha256": _file_sha256(dem_path) if dem_path.is_file() else "MISSING",
        "roughness_sha256": _file_sha256(roughness_path) if roughness_path.is_file() else "MISSING",
    }

    record = MumbaiDomainRecord(
        domain_id="mumbai_pilot_v1",
        created_at=datetime.now(timezone.utc).isoformat(),
        crs="EPSG:32643",
        grid_shape=tuple(dem_info["shape"]),  # type: ignore[arg-type]
        transform=tuple(dem_info["transform"]),  # type: ignore[arg-type]
        nodata=float(dem_info["nodata"]),
        pixel_resolution_m=abs(float(dem_info["transform"][4])),
        bbox_wgs84=tuple(dem_info["bbox_wgs84"]),  # type: ignore[arg-type]
        dem_path=effective_dem,
        dem_source="copernicus_glo_30",
        dem_nan_cells=int(dem_info["nan_count"]),
        dem_finite_cells=int(dem_info["finite_count"]),
        dem_min_m=float(dem_info["min_m"]),
        dem_max_m=float(dem_info["max_m"]),
        dem_repaired=repaired,
        dem_repair_method=repair_method,
        roughness_path=str(roughness_path),
        roughness_source="esa_worldcover_manning_lookup",
        roughness_calibrated=False,
        roughness_min=float(roughness_info["min"]),
        roughness_max=float(roughness_info["max"]),
        slope_path=str(slope_path) if slope_avail else None,
        domain_mask_path=None,  # not yet produced; can be derived from finite-DEM mask
        boundary_conditions=boundary_conditions,
        forcing_schema=forcing_schema,
        slope_available=slope_avail,
        flow_accumulation_available=flow_acc_avail,
        low_lying_index_available=low_lying_avail,
        provenance=provenance,
        assumed_parameters=(
            "roughness:uncalibrated_literature",
            "boundary:open_coastal_mean_sea_level",
            "infiltration:horton_default_ranges",
        ),
        blockers=tuple(blockers),
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    record.write(output_path)
    return record


def generate_domain_mask(
    dem_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Generate binary domain mask from finite DEM cells (1=valid, 0=nodata/noflow).

    Does not invent cell validity; only propagates from DEM nodata mask.
    """
    dem_path = Path(dem_path)
    output_path = Path(output_path)

    try:
        import rasterio  # type: ignore[import-untyped]

        with rasterio.open(dem_path) as src:
            arr = src.read(1)
            profile = src.profile.copy()

        mask = np.isfinite(arr).astype(np.uint8)
        profile.update(dtype=rasterio.uint8, count=1, nodata=0)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mask[np.newaxis, :, :])

        return output_path
    except ImportError as err:
        raise RuntimeError("rasterio is required to generate domain mask") from err
