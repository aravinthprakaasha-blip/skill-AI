"""Enable Row Level Security on all tables (blocks Supabase's public REST API).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    from app.db import lock_down_tables

    lock_down_tables(bind)


def downgrade() -> None:
    pass  # intentionally irreversible: never re-expose tables to the anon API
