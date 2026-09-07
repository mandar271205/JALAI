from pathlib import Path

from jalrakshak_ml.deep_nowcast.acquisition import HistoricalDataAcquirer


def test_default_acquisition_is_bounded_dry_run():
    config = Path("configs/training/convlstm_mumbai_v1.yaml")
    acquirer = HistoricalDataAcquirer(config)
    result = acquirer.run(execute=False)
    assert result["status"] == "DRY_RUN"
    assert result["total_planned_frames"] == 72
    assert result["estimated_download_gb"] <= result["limits"]["max_download_gb"]
    assert {event["split"] for event in result["events"]} == {"train", "validation", "test"}
