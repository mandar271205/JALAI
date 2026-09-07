from jalrakshak_ml.config import load_pilot_config


def test_mumbai_pilot_config_loads():
    pilot = load_pilot_config("configs/pilot/mumbai.yaml")
    assert pilot["name"] == "mumbai"
    assert pilot["grid"]["width"] == 256
    assert pilot["grid"]["height"] == 256
    assert pilot["api_crs"] == "EPSG:4326"
