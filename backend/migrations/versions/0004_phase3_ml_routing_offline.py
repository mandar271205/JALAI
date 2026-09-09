"""phase 3 responder tasks and offline mutations

Revision ID: 0004_phase3
Revises: 0003_phase2
Create Date: 2026-09-08 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase3"
down_revision: str | None = "0003_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update responder_tasks
    op.add_column(
        "responder_tasks",
        sa.Column("task_type", sa.String(50), nullable=False, server_default="VERIFY_LOCATION"),
    )
    op.add_column(
        "responder_tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("responder_tasks", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("responder_tasks", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("responder_tasks", sa.Column("evidence_image_url", sa.String(512), nullable=True))
    op.add_column("responder_tasks", sa.Column("measured_depth_cm", sa.Float(), nullable=True))

    # 2. Create applied_mutations
    op.create_table(
        "applied_mutations",
        sa.Column("mutation_id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACCEPTED"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_applied_mutations_client_id", "applied_mutations", ["client_id"])


def downgrade() -> None:
    op.drop_table("applied_mutations")
    op.drop_column("responder_tasks", "measured_depth_cm")
    op.drop_column("responder_tasks", "evidence_image_url")
    op.drop_column("responder_tasks", "longitude")
    op.drop_column("responder_tasks", "latitude")
    op.drop_column("responder_tasks", "version")
    op.drop_column("responder_tasks", "task_type")
