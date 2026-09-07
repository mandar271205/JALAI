import torch
from torch.utils.data import DataLoader

from jalrakshak_ml.deep_nowcast.convlstm import ConvLSTMNowcaster
from jalrakshak_ml.deep_nowcast.dataset import LogRainNormalizer, RainfallSequenceDataset
from jalrakshak_ml.deep_nowcast.inference import ConvLSTMInference
from jalrakshak_ml.deep_nowcast.train import train_model


def test_training_checkpoint_resume_and_cpu_inference(phase3_version_dir, tmp_path):
    normalizer = LogRainNormalizer.fit_from_version(phase3_version_dir)
    train = RainfallSequenceDataset(
        phase3_version_dir, split="train", history_length=4, prediction_horizon=4,
        crop_size=[4, 4], normalizer=normalizer,
    )
    validation = RainfallSequenceDataset(
        phase3_version_dir, split="validation", history_length=4, prediction_horizon=4,
        crop_size=[4, 4], normalizer=normalizer,
    )
    model = ConvLSTMNowcaster(
        input_channels=1, hidden_channels=[2], num_layers=1,
        output_horizons=4, head_channels=2,
    )
    output = tmp_path / "checkpoint"
    first = train_model(
        model, DataLoader(train, batch_size=1), DataLoader(validation, batch_size=1),
        normalizer=normalizer, output_dir=output,
        data_version="gpm_test_v1", model_version="convlstm_test",
        epochs=1, device="cpu", early_stopping_patience=2, seed=7,
    )
    assert first.best_checkpoint.exists()
    resumed_model = ConvLSTMNowcaster(
        input_channels=1, hidden_channels=[2], num_layers=1,
        output_horizons=4, head_channels=2,
    )
    second = train_model(
        resumed_model, DataLoader(train, batch_size=1), DataLoader(validation, batch_size=1),
        normalizer=normalizer, output_dir=output,
        data_version="gpm_test_v1", model_version="convlstm_test",
        epochs=2, device="cpu", early_stopping_patience=2, seed=7,
        resume_from=first.latest_checkpoint,
    )
    assert second.epochs_completed == 2
    provider = ConvLSTMInference(second.best_checkpoint, device="cpu")
    prediction = provider.predict(train.get_raw(0)["inputs"], lead_times=4)
    assert prediction.shape == (4, 4, 4)
    assert torch.isfinite(torch.from_numpy(prediction)).all()
