import pytest
import torch

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.losses import WeightedRainfallLoss


def test_convlstm_shape_and_non_negative_output():
    model = ConvLSTMNowcaster(
        input_channels=1,
        hidden_channels=[4, 4],
        num_layers=2,
        output_horizons=4,
        head_channels=4,
    )
    prediction = model(torch.randn(2, 4, 1, 8, 8))
    assert prediction.shape == (2, 4, 1, 8, 8)
    assert torch.all(prediction >= 0)


def test_convlstm_rejects_wrong_contract():
    model = ConvLSTMNowcaster(input_channels=1, hidden_channels=2, output_horizons=4)
    with pytest.raises(ValueError, match=r"\[B,T,C,H,W\]"):
        model(torch.zeros(4, 1, 8, 8))


def test_event_weighted_loss_and_missing_mask():
    loss = WeightedRainfallLoss(
        heavy_threshold=0.5,
        heavy_weight=4.0,
        mse_weight=0.0,
    )
    target = torch.tensor([[[[[0.1, 1.0]]]]])
    prediction = torch.zeros_like(target)
    mask = torch.ones_like(target, dtype=torch.bool)
    weighted = loss(prediction, target, mask)
    mask[..., 1] = False
    light_only = loss(prediction, target, mask)
    assert weighted > light_only
