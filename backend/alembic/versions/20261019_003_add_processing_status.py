"""add processing_status and processing_error to policy_versions

Revision ID: 20261019_003
Revises: 20261019_002
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa

revision: str = "20261019_003"
down_revision: str | None = "20261019_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policy_versions", sa.Column("processing_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("policy_versions", sa.Column("processing_error", sa.Text(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint("ck_policy_versions_processing_status", "policy_versions", "processing_status IN ('pending', 'processing', 'completed', 'failed')")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_policy_versions_processing_status", "policy_versions", type_="check")
    op.drop_column("policy_versions", "processing_error")
    op.drop_column("policy_versions", "processing_status")
