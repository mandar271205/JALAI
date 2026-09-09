from app.db.models import Base


def test_all_models_declared():
    tables = Base.metadata.tables
    expected_tables = {
        "users",
        "weather_sources",
        "model_runs",
        "risk_cells",
        "incidents",
        "incident_events",
        "field_reports",
        "field_report_uploads",
        "alerts",
        "critical_assets",
        "responder_tasks",
        "audit_log",
        "outbox_events",
        "raw_weather_artifacts",
        "watch_locations",
        "device_push_tokens",
        "applied_mutations",
    }
    assert expected_tables.issubset(tables.keys()), (
        f"Missing tables: {expected_tables - set(tables.keys())}"
    )
