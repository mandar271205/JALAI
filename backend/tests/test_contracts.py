import json
from pathlib import Path

import jsonschema
import yaml


def test_all_json_schemas_are_valid():
    base = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
    assert base.exists(), f"Schema dir not found: {base}"
    for schema_file in base.glob("*.schema.json"):
        with open(schema_file) as f:
            schema = json.load(f)
        jsonschema.Draft7Validator.check_schema(schema)


def test_demo_fixtures_validate_against_schemas():
    base = Path(__file__).resolve().parents[2] / "contracts"
    fixtures_dir = base / "fixtures" / "demo-event"
    schemas_dir = base / "schemas"

    mapping = [
        ("risk-cell.schema.json", "risk-cells.json", True),
        ("incident.schema.json", "incidents.json", True),
        ("field-report.schema.json", "reports.json", True),
        ("nowcast-manifest.schema.json", "nowcast-manifest.json", False),
        ("inundation-manifest.schema.json", "inundation-manifest.json", False),
        ("weather-source.schema.json", "weather-sources.json", True),
        ("alert.schema.json", "alerts.json", True),
        ("critical-asset.schema.json", "critical-assets.json", True),
    ]

    for schema_name, fixture_name, is_list in mapping:
        with open(schemas_dir / schema_name) as sf, open(fixtures_dir / fixture_name) as ff:
            schema = json.load(sf)
            data = json.load(ff)
            if is_list:
                for item in data:
                    jsonschema.validate(instance=item, schema=schema)
            else:
                jsonschema.validate(instance=data, schema=schema)


def test_openapi_spec_has_required_endpoints():
    base = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"
    with open(base) as f:
        spec = yaml.safe_load(f)

    paths = spec.get("paths", {})
    required_paths = [
        "/health",
        "/ready",
        "/api/v1/weather/current",
        "/api/v1/weather/sources/status",
        "/api/v1/nowcast/manifest",
        "/api/v1/inundation/manifest",
        "/api/v1/risk/cells",
        "/api/v1/incidents",
        "/api/v1/reports",
        "/api/v1/routes/lower-risk",
        "/api/v1/alerts/draft",
    ]
    for path in required_paths:
        assert path in paths, f"Path {path} missing from contracts/openapi.yaml"
