"""Add import tracking tables.

Revision ID: 20260819_000002
Revises: 20260812_000001
Create Date: 2026-08-19 00:00:02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260819_000002"
down_revision = "20260812_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_run",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("profile", sa.Text(), nullable=True),
        sa.Column("dataset_api_path", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("phase", sa.Text(), nullable=True),
        sa.Column("total_features", sa.Integer(), nullable=True),
        sa.Column("processed_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_error",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="gc_jobs",
    )
    op.create_table(
        "import_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("import_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["gc_jobs.import_run.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="gc_jobs",
    )
    op.create_index(
        "ix_gc_jobs_import_run_last_event_at",
        "import_run",
        ["last_event_at"],
        schema="gc_jobs",
    )
    op.create_index(
        "ix_gc_jobs_import_event_import_id_id",
        "import_event",
        ["import_id", "id"],
        schema="gc_jobs",
    )
    op.create_index(
        "ux_gc_jobs_import_event_message_id",
        "import_event",
        ["message_id"],
        unique=True,
        schema="gc_jobs",
    )


def downgrade() -> None:
    op.drop_index("ux_gc_jobs_import_event_message_id", table_name="import_event", schema="gc_jobs")
    op.drop_index("ix_gc_jobs_import_event_import_id_id", table_name="import_event", schema="gc_jobs")
    op.drop_index("ix_gc_jobs_import_run_last_event_at", table_name="import_run", schema="gc_jobs")
    op.drop_table("import_event", schema="gc_jobs")
    op.drop_table("import_run", schema="gc_jobs")