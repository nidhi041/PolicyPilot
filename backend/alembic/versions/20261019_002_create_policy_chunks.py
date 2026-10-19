"""create policy_chunks table with pgvector support

Revision ID: 20261019_002
Revises: 20261019_001
Create Date: 2026-10-19
"""
from typing import Sequence, Union
from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision: str = "20261019_002"
down_revision: Union[str, None] = "20261019_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("policy_version_id", sa.Uuid(), sa.ForeignKey("policy_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("policy_version_id", "chunk_index", name="uq_policy_chunks_version_chunk_index"),
        sa.CheckConstraint("page_number >= 1", name="ck_policy_chunks_page_number"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_policy_chunks_chunk_index"),
    )
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_policy_chunks_embedding_hnsw ON policy_chunks USING hnsw (embedding vector_cosine_ops);")


def downgrade() -> None:
    op.drop_table("policy_chunks")
