"""Phase-3 trainable deep rainfall-nowcasting pipeline."""

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, RainfallSequenceDataset
from jalrakshak_ml.deep_nowcast.losses import HeavyRainAwareLoss, WeightedRainfallLoss
from jalrakshak_ml.deep_nowcast.residual_convlstm import (
    PersistenceResidualConvLSTMNowcaster,
    reconstruct_persistence_residual,
)

__all__ = [
    "ConvLSTMNowcaster",
    "HeavyRainAwareLoss",
    "LogRainNormalizer",
    "PersistenceResidualConvLSTMNowcaster",
    "RainfallSequenceDataset",
    "WeightedRainfallLoss",
    "reconstruct_persistence_residual",
]
