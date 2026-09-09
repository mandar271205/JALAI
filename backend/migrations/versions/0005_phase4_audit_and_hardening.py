"""phase 4 audit cryptographic fields and region scoping

Revision ID: 0005_phase4
Revises: 0004_phase3
Create Date: 2026-09-08 15:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase4"
down_revision: str | None = "0004_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add region to users
    op.add_column(
        "users", sa.Column("region", sa.String(100), nullable=True, server_default="mumbai")
    )

    # 2. Add region to incidents
    op.add_column(
        "incidents", sa.Column("region", sa.String(100), nullable=True, server_default="mumbai")
    )
    op.create_index("ix_incidents_region", "incidents", ["region"])

    # 3. Add cryptographic audit fields to audit_log
    op.add_column("audit_log", sa.Column("actor_role", sa.String(50), nullable=True))
    op.add_column("audit_log", sa.Column("trace_id", sa.String(64), nullable=True))
    op.create_index("ix_audit_log_trace_id", "audit_log", ["trace_id"])
    op.add_column("audit_log", sa.Column("before_hash", sa.String(64), nullable=True))
    op.add_column("audit_log", sa.Column("after_hash", sa.String(64), nullable=True))
    op.add_column("audit_log", sa.Column("supporting_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_log", "supporting_snapshot")
    op.drop_column("audit_log", "after_hash")
    op.drop_column("audit_log", "before_hash")
    op.drop_index("ix_audit_log_trace_id", "audit_log")
    op.drop_column("audit_log", "trace_id")
    op.drop_column("audit_log", "actor_role")

    op.drop_index("ix_incidents_region", "incidents")
    op.drop_column("incidents", "region")

    op.drop_column("users", "region")
