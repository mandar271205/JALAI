from __future__ import annotations

import importlib
import sys

packages = [
    "numpy",
    "pandas",
    "xarray",
    "zarr",
    "rasterio",
    "rioxarray",
    "geopandas",
    "shapely",
    "pyproj",
    "pydantic",
    "yaml",
]

print("Python:", sys.version)
failed = []

for pkg in packages:
    try:
        mod = importlib.import_module(pkg)
        version = getattr(mod, "__version__", "unknown")
        print(f"[OK] {pkg}: {version}")
    except Exception as exc:
        failed.append((pkg, str(exc)))
        print(f"[FAIL] {pkg}: {exc}")

if failed:
    raise SystemExit(1)

print("\nEnvironment looks ready for Sprint 0.")
