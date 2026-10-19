"""update policy_chunks vector dimension to 768

Revision ID: 20261019_004
Revises: 20261019_003
Create Date: 2026-10-19
"""
from alembic import op

revision = "20261019_004"
down_revision = "20261019_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_policy_chunks_embedding_hnsw;")
        op.execute("ALTER TABLE policy_chunks ALTER COLUMN embedding TYPE vector(768);")
        op.execute("CREATE INDEX IF NOT EXISTS ix_policy_chunks_embedding_hnsw ON policy_chunks USING hnsw (embedding vector_cosine_ops);")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_policy_chunks_embedding_hnsw;")
        op.execute("ALTER TABLE policy_chunks ALTER COLUMN embedding TYPE vector(1536);")
        op.execute("CREATE INDEX IF NOT EXISTS ix_policy_chunks_embedding_hnsw ON policy_chunks USING hnsw (embedding vector_cosine_ops);")
