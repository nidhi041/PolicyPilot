"""create profiles table

Revision ID: 20261015_001
Revises:
Create Date: 2026-10-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261015_001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), unique=True, nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="employee"),
        sa.Column("region", sa.String(32), nullable=False, server_default="GLOBAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('employee', 'hr_administrator')", name="ck_profiles_role"),
        sa.CheckConstraint("region IN ('GLOBAL', 'US', 'EU', 'UK', 'APAC', 'EMEA', 'CA', 'LATAM', 'IN')", name="ck_profiles_region"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth' AND table_name = 'users') THEN
                    ALTER TABLE profiles ADD CONSTRAINT fk_profiles_user_id_auth_users FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("profiles")
