"""create policies and policy_versions tables

Revision ID: 20261019_001
Revises: 20261016_001
Create Date: 2026-10-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261019_001"
down_revision: Union[str, None] = "20261016_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("region", sa.String(32), nullable=False, server_default="GLOBAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("region IN ('GLOBAL', 'US', 'EU', 'UK', 'APAC', 'EMEA', 'CA', 'LATAM', 'IN')", name="ck_policies_region"),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_label", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("policy_id", "version_label", name="uq_policy_versions_policy_id_version_label"),
        sa.CheckConstraint("status IN ('draft', 'under_review', 'published', 'archived')", name="ck_policy_versions_status"),
        sa.CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_policy_versions_effective_dates"),
    )


def downgrade() -> None:
    op.drop_table("policy_versions")
    op.drop_table("policies")
