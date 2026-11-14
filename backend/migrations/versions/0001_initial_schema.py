"""Initial SkillForge schema (all tables, pgvector extension and vector index).

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""
from alembic import op

from app import models  # noqa: F401
from app.db import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Baseline: materialise the declared models as of this revision. Later revisions use op.* deltas.
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_resources_embedding_hnsw "
            "ON resources USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
