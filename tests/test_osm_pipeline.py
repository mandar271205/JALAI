"""Tests for OSM pipeline outputs."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio

STATIC_DIR = Path("data/processed/static")
EXPECTED_GEOJSONS = ["roads.geojson", "waterways.geojson", "emergency_assets.geojson"]


@pytest.mark.skipif(
    not (STATIC_DIR / "osm_manifest.json").exists(),
    reason="OSM pipeline not yet run — execute: python -m jalrakshak_ml.pipelines.osm_pipeline"
)
class TestOSMPipelineOutputs:

    def test_manifest_exists(self):
        manifest_path = STATIC_DIR / "osm_manifest.json"
        assert manifest_path.exists(), "osm_manifest.json missing"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["source"] == "openstreetmap"
        assert "bbox_wgs84" in manifest
        assert "feature_counts" in manifest
        assert "checksums" in manifest

    def test_geojsons_exist_and_valid_crs(self):
        for fname in EXPECTED_GEOJSONS:
            path = STATIC_DIR / fname
            assert path.exists(), f"{fname} missing"
            gdf = gpd.read_file(str(path))
            assert gdf.crs is not None, f"{fname} has no CRS"
            assert gdf.crs.to_epsg() == 4326, f"{fname} CRS is not EPSG:4326"
            assert len(gdf) > 0, f"{fname} is empty"

    def test_distance_to_water_raster(self):
        path = STATIC_DIR / "distance_to_water.tif"
        assert path.exists(), "distance_to_water.tif missing"
        with rasterio.open(path) as src:
            assert src.crs.to_epsg() == 32643, "distance_to_water CRS should be EPSG:32643"
            assert src.width == 256, "distance_to_water width should be 256"
            assert src.height == 256, "distance_to_water height should be 256"
            arr = src.read(1)
            assert not np.all(arr == 0), "distance_to_water is entirely zero"
            assert arr.min() >= 0.0, "distance values should be non-negative"

    def test_roads_has_geometry(self):
        roads_path = STATIC_DIR / "roads.geojson"
        if roads_path.exists():
            gdf = gpd.read_file(str(roads_path))
            assert gdf.geometry.notna().any(), "roads.geojson has no valid geometries"

    def test_hospitals_or_emergency_assets(self):
        ea_path = STATIC_DIR / "emergency_assets.geojson"
        if ea_path.exists():
            gdf = gpd.read_file(str(ea_path))
            assert "category" in gdf.columns, "emergency_assets missing 'category' column"
