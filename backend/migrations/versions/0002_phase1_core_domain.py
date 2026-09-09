"""phase 1 core domain incident events and uploads

Revision ID: 0002_phase1
Revises: 0001_initial
Create Date: 2026-09-08 15:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase1"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add probability to risk_cells
    op.add_column(
        "risk_cells", sa.Column("probability", sa.Float(), nullable=False, server_default="0.5")
    )

    # 2. Create incident_events (append-only timeline)
    op.create_table(
        "incident_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(36),
            sa.ForeignKey("incidents.incident_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("previous_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_index("ix_incident_events_created_at", "incident_events", ["created_at"])

    # 3. Create field_report_uploads (direct S3 signed upload tracking)
    op.create_table(
        "field_report_uploads",
        sa.Column("upload_id", sa.String(36), primary_key=True),
        sa.Column("citizen_id", sa.String(100), nullable=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("field_reports.report_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="image/jpeg"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256_checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("presigned_url", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_field_report_uploads_report_id", "field_report_uploads", ["report_id"])


def downgrade() -> None:
    op.drop_table("field_report_uploads")
    op.drop_table("incident_events")
    op.drop_column("risk_cells", "probability")
