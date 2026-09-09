"""initial schema with postgis and uuid

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-08 15:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions (PostgreSQL only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, default="CITIZEN"),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # 2. weather_sources
    op.create_table(
        "weather_sources",
        sa.Column("source_id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="HEALTHY"),
        sa.Column("last_successful_ingestion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_seconds", sa.Float, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. model_runs
    op.create_table(
        "model_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("model_type", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("data_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column("metrics_json", sa.JSON, nullable=True),
    )
    op.create_index("ix_model_runs_model_type", "model_runs", ["model_type"])
    op.create_index("ix_model_runs_status", "model_runs", ["status"])

    # 4. risk_cells
    op.create_table(
        "risk_cells",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("h3_cell_id", sa.String(20), nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("flood_depth_m", sa.Float, nullable=True),
        sa.Column("rainfall_rate_mm_h", sa.Float, nullable=True),
        sa.Column("ward_id", sa.String(100), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("data_version", sa.String(50), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("h3_cell_id", "valid_time", name="uq_risk_cell_valid_time"),
    )
    op.create_index("ix_risk_cells_h3_cell_id", "risk_cells", ["h3_cell_id"])
    op.create_index("ix_risk_cells_valid_time", "risk_cells", ["valid_time"])
    op.create_index("ix_risk_cells_risk_level", "risk_cells", ["risk_level"])
    op.create_index("ix_risk_cells_ward_id", "risk_cells", ["ward_id"])

    # 5. incidents
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, default="HIGH"),
        sa.Column("status", sa.String(30), nullable=False, default="REPORTED"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("ward_id", sa.String(100), nullable=True),
        sa.Column("reporter_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])

    # 6. field_reports
    op.create_table(
        "field_reports",
        sa.Column("report_id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("incidents.incident_id"), nullable=True
        ),
        sa.Column("citizen_id", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=False, default="PENDING"),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("estimated_water_depth_cm", sa.Float, nullable=True),
        sa.Column("verified_by", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_field_reports_incident_id", "field_reports", ["incident_id"])
    op.create_index(
        "ix_field_reports_verification_status", "field_reports", ["verification_status"]
    )
    op.create_index("ix_field_reports_submitted_at", "field_reports", ["submitted_at"])

    # 7. alerts
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(36), primary_key=True),
        sa.Column("headline", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("instruction", sa.Text, nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("urgency", sa.String(20), nullable=False),
        sa.Column("certainty", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, default="DRAFT"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("area_description", sa.String(255), nullable=False),
        sa.Column("geom", Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True),
        sa.Column("cap_xml", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"])

    # 8. critical_assets
    op.create_table(
        "critical_assets",
        sa.Column("asset_id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("flood_threshold_m", sa.Float, nullable=False, default=0.5),
        sa.Column("status", sa.String(50), nullable=False, default="NORMAL"),
        sa.Column("metadata_json", sa.JSON, nullable=True),
    )

    # 9. responder_tasks
    op.create_table(
        "responder_tasks",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id", sa.String(36), sa.ForeignKey("incidents.incident_id"), nullable=False
        ),
        sa.Column("responder_id", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, default="HIGH"),
        sa.Column("status", sa.String(30), nullable=False, default="ASSIGNED"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instructions", sa.Text, nullable=True),
    )
    op.create_index("ix_responder_tasks_incident_id", "responder_tasks", ["incident_id"])
    op.create_index("ix_responder_tasks_responder_id", "responder_tasks", ["responder_id"])
    op.create_index("ix_responder_tasks_status", "responder_tasks", ["status"])

    # 10. audit_log
    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_entity", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("changes_json", sa.JSON, nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])

    # 11. outbox_events
    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("processed", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_events_processed", "outbox_events", ["processed"])
    op.create_index("ix_outbox_events_created_at", "outbox_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("audit_log")
    op.drop_table("responder_tasks")
    op.drop_table("critical_assets")
    op.drop_table("alerts")
    op.drop_table("field_reports")
    op.drop_table("incidents")
    op.drop_table("risk_cells")
    op.drop_table("model_runs")
    op.drop_table("weather_sources")
    op.drop_table("users")
