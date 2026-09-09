"""phase 2 ingestion alerts and watch locations

Revision ID: 0003_phase2
Revises: 0002_phase1
Create Date: 2026-09-08 15:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase2"
down_revision: str | None = "0002_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. raw_weather_artifacts
    op.create_table(
        "raw_weather_artifacts",
        sa.Column("artifact_id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("raw_storage_uri", sa.String(512), nullable=False),
        sa.Column("normalized_uri", sa.String(512), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("is_immutable", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_raw_weather_artifacts_source_id", "raw_weather_artifacts", ["source_id"])
    op.create_index(
        "ix_raw_weather_artifacts_source_timestamp", "raw_weather_artifacts", ["source_timestamp"]
    )

    # 2. watch_locations
    op.create_table(
        "watch_locations",
        sa.Column("location_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("h3_cell_id", sa.String(20), nullable=True),
        sa.Column("ward_id", sa.String(100), nullable=True),
        sa.Column("risk_threshold", sa.String(20), nullable=False, server_default="HIGH"),
        sa.Column("notify_push", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watch_locations_user_id", "watch_locations", ["user_id"])
    op.create_index("ix_watch_locations_h3_cell_id", "watch_locations", ["h3_cell_id"])

    # 3. device_push_tokens
    op.create_table(
        "device_push_tokens",
        sa.Column("token_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("expo_push_token", sa.String(255), unique=True, nullable=False),
        sa.Column("device_os", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_push_tokens_user_id", "device_push_tokens", ["user_id"])
    op.create_index(
        "ix_device_push_tokens_expo_push_token", "device_push_tokens", ["expo_push_token"]
    )

    # 4. alerts additions
    op.add_column("alerts", sa.Column("approved_by", sa.String(100), nullable=True))
    op.add_column("alerts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("source_risk_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("alerts", sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "expires_at")
    op.drop_column("alerts", "effective_at")
    op.drop_column("alerts", "source_risk_snapshot_json")
    op.drop_column("alerts", "approved_at")
    op.drop_column("alerts", "approved_by")
    op.drop_table("device_push_tokens")
    op.drop_table("watch_locations")
    op.drop_table("raw_weather_artifacts")
