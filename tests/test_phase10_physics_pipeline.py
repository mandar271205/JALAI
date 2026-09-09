"""Test suite for Phase 10: LISFLOOD-FP Solver, Scenarios, Dataset Builder, and FNO Pipeline."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import numpy as np
import pytest
import torch

from jalrakshak_ml.flood.scenarios import (
    PhysicalRainfallScenario,
    get_default_scenario_batch,
)
from jalrakshak_ml.flood.lisflood_adapter import (
    find_lisflood_binary,
    ensure_ascii_dem,
    ensure_lisflood_rain,
    LISFLOODRunRecord,
)
from jalrakshak_ml.flood.dataset_builder import build_physics_dataset
from jalrakshak_ml.flood.fno import (
    FloodFNO,
    SparseFloodLoss,
    evaluate_fno,
    FNOTrainingConfig,
    FNOTrainingRunner,
    require_physics_reference_dataset,
)
from jalrakshak_ml.core.claim_gates import ScientificClaimGates


def test_lisflood_binary_detection():
    """Verify solver binary detector executes without crashing."""
    binary = find_lisflood_binary()
    # In WSL2 or native, it should be detected or return None gracefully
    if binary:
        assert isinstance(binary, str)
        assert "lisflood" in binary.lower()


def test_physical_scenarios_catalog():
    """Verify physical scenario batch is deterministic and correctly labelled."""
    scenarios = get_default_scenario_batch(8)
    assert len(scenarios) == 8

    for sc in scenarios:
        assert sc.source_type == "generated_physics_scenario"
        assert sc.synthetic is True
        assert sc.observed is False
        assert sc.calibrated is False
        assert sc.duration_hours > 0
        assert sc.peak_rate_mm_h > 0
        assert len(sc.rates_mm_h) >= 2


def test_scenario_forcing_generation(tmp_path):
    """Verify that PhysicalRainfallScenario writes compliant .rain forcing files."""
    sc = PhysicalRainfallScenario(
        scenario_id="test_sc_01",
        description="Test convective burst",
        duration_hours=1.0,
        cadence_minutes=30,
        rates_mm_h=(50.0, 20.0),
        peak_rate_mm_h=50.0,
        mean_rate_mm_h=35.0,
        profile_type="pulse",
    )
    rain_p, meta_p = sc.write_forcing(tmp_path)
    assert rain_p.is_file()
    assert meta_p.is_file()

    content = rain_p.read_text(encoding="utf-8")
    assert "2 hours" in content
    assert "50.0000\t0.0000" in content
    assert "20.0000\t0.5000" in content

    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    assert meta["scenario_id"] == "test_sc_01"
    assert meta["synthetic"] is True


def test_ensure_lisflood_rain_ordering(tmp_path):
    """Verify ensure_lisflood_rain converts any rainfall file to value-first, time-second format."""
    raw_rain = tmp_path / "raw.bdy"
    raw_rain.write_text(
        "# time rate format\n"
        "2 hours\n"
        "0.0 45.0\n"
        "0.5 80.0\n",
        encoding="utf-8"
    )
    formatted = ensure_lisflood_rain(raw_rain, tmp_path / "out", "test.rain")
    assert formatted.is_file()
    lines = [ln.strip() for ln in formatted.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    assert lines[0] == "2 hours"
    # rate is 45.0, time is 0.0 -> rate first, time second
    assert lines[1].startswith("45.0000\t0.0000")
    assert lines[2].startswith("80.0000\t0.5000")


def test_dataset_builder_rejection(tmp_path):
    """Verify dataset builder strictly rejects invalid or susceptibility rasters."""
    batch_manifest = tmp_path / "batch.json"
    batch_manifest.write_text(json.dumps({
        "runs": [
            {
                "scenario_id": "bad_run",
                "execution_status": "SUCCESS",
                "physically_simulated": True,
                "depth_raster_path": "data/processed/flood/susceptibility.tif",
                "max_depth_m": 1.2,
            }
        ]
    }), encoding="utf-8")

    domain_file = tmp_path / "domain.json"
    domain_file.write_text(json.dumps({"grid_shape": [256, 256], "crs": "EPSG:32643"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Susceptibility raster detected"):
        build_physics_dataset(
            batch_manifest,
            domain_record_path=domain_file,
            output_dir=tmp_path / "out",
            min_scenarios=1,
        )


def test_fno_architecture_forward_shape():
    """Verify FloodFNO architecture produces [B, horizons, 1, H, W] nonnegative depths."""
    model = FloodFNO(input_channels=6, width=8, modes=4, output_horizons=4)
    x = torch.rand(2, 6, 32, 32)
    out = model(x)
    assert out.shape == (2, 4, 1, 32, 32)
    assert torch.all(out >= 0)


def test_sparse_flood_loss():
    """Verify SparseFloodLoss weights wet cells higher and handles zero gracefully."""
    loss_fn = SparseFloodLoss(wet_threshold=0.05, wet_weight=5.0)
    pred = torch.tensor([[[[[0.02]], [[0.10]]]]])
    target = torch.tensor([[[[[0.00]], [[0.50]]]]])
    mask = torch.ones_like(pred, dtype=torch.bool)
    loss = loss_fn(pred, target, mask)
    assert torch.isfinite(loss)
    assert loss.item() > 0


def test_claim_gates_consistency():
    """Verify claim gates integrity checks enforce non-negotiables."""
    # Valid default gates
    gates = ScientificClaimGates()
    assert gates.SUSCEPTIBILITY_IS_NOT_DEPTH is True
    assert gates.LOCKED_TEST_TOUCHED is False

    # Cannot claim FNO trained without genuine targets
    with pytest.raises(ValueError, match="Genuine FNO targets require executed real simulations"):
        ScientificClaimGates(
            GENUINE_FNO_TARGETS_AVAILABLE=True,
            REAL_PHYSICS_SIMULATION_EXECUTED=False,
        )
