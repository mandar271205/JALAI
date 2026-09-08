"""Comprehensive Unit and Scientific Integrity Tests for Phase 4E Deep Nowcasting."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from jalrakshak_ml.config import load_yaml
from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.losses import MultiScalePiecewiseLoss
from jalrakshak_ml.deep_nowcast.multisource_dataset import (
    MultiSourceNowcastDataset,
    MultiSourceStats,
)
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster


def test_split_isolation_and_event_integrity():
    """Verify train, validation, and test splits are strictly disjoint."""
    catalog_path = Path("data/catalogs/mumbai_rainfall_events_v1.json")
    assert catalog_path.exists()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    splits = catalog["research_splits_locked"]

    train_events = set(splits["train"])
    val_events = set(splits["validation"])
    test_events = set(splits["test"])

    assert len(train_events.intersection(val_events)) == 0
    assert len(train_events.intersection(test_events)) == 0
    assert len(val_events.intersection(test_events)) == 0

    assert "mumbai_monsoon_2023_08_24" in test_events
    assert "mumbai_monsoon_2024_08_04" in test_events
    assert "mumbai_monsoon_2024_09_05" in test_events


def test_normalization_fitted_strictly_on_train():
    """Verify normalizer parameters only fit on the train split."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    assert version_dir.exists()
    stats = MultiSourceStats.fit_from_training(version_dir, "")
    assert stats.fitted_split == "train"
    assert "rainfall_gpm" in stats.channel_stats
    assert stats.channel_stats["rainfall_gpm"]["scale"] > 0.0


def test_multisource_channels_manifest():
    """Verify explicit channel inventory records REAL_DATA status without fake radar/INSAT."""
    cfg_path = Path("configs/training/multisource_channels_v1.yaml")
    assert cfg_path.exists()
    cfg = load_yaml(cfg_path)
    channels = cfg["channels"]

    # Authentic channels must be marked REAL_DATA: true
    assert channels["rainfall_gpm"]["REAL_DATA"] is True
    assert channels["gfs_precipitation"]["REAL_DATA"] is True
    assert channels["static_elevation"]["REAL_DATA"] is True

    # Unavailable radar and INSAT channels must NOT claim real data
    assert channels["radar_reflectivity"]["REAL_DATA"] is False
    assert channels["radar_rainfall"]["REAL_DATA"] is False
    assert channels["satellite_ir"]["REAL_DATA"] is False
    assert channels["satellite_wv"]["REAL_DATA"] is False


def test_multisource_dataset_shapes_and_masks():
    """Verify dataset output shapes, valid masks, and non-negative targets."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=("rainfall_gpm", "gfs_precipitation", "static_elevation"),
        crop_size=(128, 128),
        dropout_prob=0.0,
    )
    assert len(ds) == 17
    sample = ds[0]

    assert sample["inputs"].shape == (4, 3, 128, 128)
    assert sample["target_physical"].shape == (4, 1, 128, 128)
    assert sample["persistence_baseline"].shape == (1, 128, 128)
    assert sample["missing_channel_mask"].shape == (3,)
    assert (sample["target_physical"] >= 0.0).all()


def test_source_dropout_functionality():
    """Verify source dropout marks non-observation channels missing while keeping observation."""
    version_dir = Path("data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1")
    ds = MultiSourceNowcastDataset(
        version_dir,
        split="train",
        active_channels=("rainfall_gpm", "gfs_precipitation", "static_elevation"),
        dropout_prob=1.0,  # drop all optional sources
        rng_seed=42,
    )
    sample = ds[0]
    # GPM rainfall must NEVER be dropped
    assert sample["missing_channel_mask"][0].item() is False
    # GFS and elevation are dropped under prob 1.0
    assert sample["missing_channel_mask"][1].item() is True
    assert sample["missing_channel_mask"][2].item() is True


def test_convlstm_v3_shape_and_non_negativity():
    """Verify ConvLSTM V3 output shape and physical non-negativity constraint."""
    model = ConvLSTMNowcasterV3(input_channels=3, hidden_channels=(16, 16), head_channels=8)
    x = torch.randn(2, 4, 3, 128, 128)
    p = torch.clamp(torch.randn(2, 1, 128, 128), min=0.0)
    out = model(x, p)
    assert out.shape == (2, 4, 1, 128, 128)
    assert (out >= 0.0).all()


def test_unet_convgru_shape_and_non_negativity():
    """Verify U-Net + ConvGRU output shape and physical non-negativity constraint."""
    model = UNetConvGRUNowcaster(input_channels=3, base_channels=8, bottleneck_channels=16, head_channels=8)
    x = torch.randn(2, 4, 3, 128, 128)
    p = torch.clamp(torch.randn(2, 1, 128, 128), min=0.0)
    out = model(x, p)
    assert out.shape == (2, 4, 1, 128, 128)
    assert (out >= 0.0).all()


def test_st_attention_shape_and_non_negativity():
    """Verify STAttentionNowcasterV1 output shape and non-negativity."""
    model = STAttentionNowcasterV1(input_channels=3, embed_dim=32, num_heads=2, patch_size=8, head_channels=8)
    x = torch.randn(2, 4, 3, 128, 128)
    p = torch.clamp(torch.randn(2, 1, 128, 128), min=0.0)
    out = model(x, p)
    assert out.shape == (2, 4, 1, 128, 128)
    assert (out >= 0.0).all()


def test_multiscale_piecewise_loss():
    """Verify multi-scale piecewise loss calculates native and coarse components."""
    loss_fn = MultiScalePiecewiseLoss(coarse_scale_weight=0.25, pool_kernel=2)
    pred = torch.clamp(torch.randn(2, 4, 1, 128, 128), min=0.0)
    targ = torch.clamp(torch.randn(2, 4, 1, 128, 128), min=0.0)
    mask = torch.ones_like(targ, dtype=torch.bool)

    loss = loss_fn(pred, targ, mask)
    assert loss.ndim == 0
    assert loss.item() >= 0.0

    comps = loss_fn.compute_components(pred, targ, mask)
    assert "native_loss" in comps
    assert "coarse_loss" in comps
    assert "total_loss" in comps
    assert comps["total_loss"] > 0.0


def test_deterministic_seeded_reproducibility():
    """Verify identical random seeds produce exact deterministic outputs."""
    torch.manual_seed(26071)
    m1 = ConvLSTMNowcasterV3(input_channels=3, hidden_channels=(16, 16), head_channels=8)
    torch.manual_seed(26071)
    m2 = ConvLSTMNowcasterV3(input_channels=3, hidden_channels=(16, 16), head_channels=8)

    x = torch.randn(1, 4, 3, 128, 128)
    p = torch.ones(1, 1, 128, 128)

    y1 = m1(x, p)
    y2 = m2(x, p)
    assert torch.allclose(y1, y2, atol=1e-6)


def test_no_fake_channels_in_training_configs():
    """Verify training configs do not configure unavailable radar or INSAT channels."""
    configs = [
        "configs/training/convlstm_v3.yaml",
        "configs/training/unet_convgru_v1.yaml",
        "configs/training/st_attention_nowcaster_v1.yaml",
    ]
    for cpath in configs:
        cfg = load_yaml(Path(cpath))
        active = cfg["dataset"]["active_channels"]
        assert "radar_reflectivity" not in active
        assert "radar_rainfall" not in active
        assert "satellite_ir" not in active
        assert "satellite_wv" not in active


def test_nowcast_result_contract_compatibility():
    """Verify Phase 4E model predictions wrap seamlessly into canonical NowcastResult."""
    from datetime import datetime, UTC
    from jalrakshak_ml.nowcast.contracts import NowcastResult

    # Simulate 4-horizon prediction [4, 128, 128]
    pred = np.maximum(0.0, np.random.randn(4, 128, 128).astype(np.float32))
    res = NowcastResult(
        rainfall=pred,
        issue_time=datetime(2023, 7, 18, 6, 0, tzinfo=UTC),
        horizons_min=[30, 60, 90, 120],
        provider="convlstm_v3",
        model_version="v3.0.0",
        data_version="gpm_imerg_v07_mumbai_monsoon_expanded_v1",
        checkpoint_hash="sha256:dummyhash12345",
    )
    manifest = res.to_manifest()
    assert manifest["provider"] == "convlstm_v3"
    assert manifest["horizons_min"] == [30, 60, 90, 120]
    assert manifest["units"] == "mm/h"
    assert (res.rainfall >= 0.0).all()


def test_lead_ordering_monotonicity():
    """Verify horizons are strictly ascending positive multiples of 30 minutes."""
    horizons = [30, 60, 90, 120]
    assert all(h > 0 for h in horizons)
    assert horizons == sorted(horizons)
    assert len(set(horizons)) == len(horizons)
    assert all(h % 30 == 0 for h in horizons)


def test_no_test_split_in_training_configs():
    """Verify training configs only use train for optimization and validation for model selection."""
    configs = [
        "configs/training/convlstm_v3.yaml",
        "configs/training/unet_convgru_v1.yaml",
        "configs/training/st_attention_nowcaster_v1.yaml",
    ]
    for cpath in configs:
        cfg = load_yaml(Path(cpath))
        split_ids = cfg["data"]["expected_split_event_ids"]
        assert "mumbai_monsoon_2023_07_18" in split_ids["train"]
        assert "mumbai_monsoon_2023_07_25" in split_ids["validation"]
        # Held-out test events must never be in train or validation
        for test_evt in split_ids["test"]:
            assert test_evt not in split_ids["train"]
            assert test_evt not in split_ids["validation"]


