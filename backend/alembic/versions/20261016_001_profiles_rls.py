"""add row level security policies to profiles

Revision ID: 20261016_001
Revises: 20261015_001
Create Date: 2026-10-16
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20261016_001"
down_revision: Union[str, None] = "20261015_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'profiles_select_own'
                ) THEN
                    CREATE POLICY profiles_select_own ON profiles
                        FOR SELECT TO authenticated
                        USING (auth.uid() = user_id);
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'profiles_update_own'
                ) THEN
                    CREATE POLICY profiles_update_own ON profiles
                        FOR UPDATE TO authenticated
                        USING (auth.uid() = user_id)
                        WITH CHECK (auth.uid() = user_id);
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            DROP POLICY IF EXISTS profiles_update_own ON profiles;
            DROP POLICY IF EXISTS profiles_select_own ON profiles;
            ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;
            """
        )
