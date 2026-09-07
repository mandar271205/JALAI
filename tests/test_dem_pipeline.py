import json
from pathlib import Path

import numpy as np
import pytest
import rasterio


def test_dem_pipeline_outputs():
    static_dir = Path("data/processed/static")
    
    expected_tiffs = [
        "elevation.tif",
        "slope.tif",
        "flow_accumulation.tif",
        "low_lying_index.tif"
    ]
    
    for tif_file in expected_tiffs:
        path = static_dir / tif_file
        assert path.exists(), f"{tif_file} not generated"
        
        with rasterio.open(path) as src:
            assert src.crs.to_string() == "EPSG:32643"
            assert src.shape == (256, 256)
            data = src.read(1)
            # Ensure not completely empty/nan
            assert not np.all(np.isnan(data)), f"{tif_file} is entirely NaN"
            
    assert (static_dir / "elevation.npy").exists()
    
    manifest_path = static_dir / "dem_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_crs"] == "EPSG:4326"
    assert "checksum" in manifest
    
    terrain_manifest = static_dir / "terrain_manifest.json"
    assert terrain_manifest.exists()
    t_manifest = json.loads(terrain_manifest.read_text())
    assert "low_lying_index" in t_manifest["features_generated"]
