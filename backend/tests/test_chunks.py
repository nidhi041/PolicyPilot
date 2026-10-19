"""Unit, migration, and repository tests for policy_chunks and pgvector embedding storage."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import uuid
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db.models import Base, Policy, PolicyChunk, PolicyVersion
from app.db.repository import PolicyChunkRepository, policy_chunk_repo


@pytest.fixture
def sqlite_session():
    engine = sa.create_engine("sqlite:///:memory:")
    # Enable SQLite foreign key constraints
    with engine.connect() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(sa.text("PRAGMA foreign_keys=ON;"))
        yield session
    Base.metadata.drop_all(engine)


def test_embedding_model_dimensions_match_column():
    settings = get_settings()
    column_dim = getattr(PolicyChunk.embedding.type, "dim", None)
    assert column_dim == 1536
    assert settings.embedding_dimensions == column_dim
    assert policy_chunk_repo.validate_dimensions_match_column() is True


def test_vector_dimension_validation():
    repo = PolicyChunkRepository(expected_dim=1536)
    valid_emb = [0.01] * 1536
    repo.validate_embedding(valid_emb)

    for bad in [[0.1] * 512, [], [0.0] * 1537]:
        with pytest.raises(ValueError, match="dimension mismatch"):
            repo.validate_embedding(bad)


@pytest.mark.asyncio
async def test_repository_save_and_retrieve_chunks(sqlite_session):
    p = Policy(title="Security Policy", category="IT", region="GLOBAL")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="/p.pdf", content_hash="h1")
    sqlite_session.add(p)
    sqlite_session.add(v)
    sqlite_session.commit()

    repo = PolicyChunkRepository(expected_dim=1536)
    chunks_data = [
        {"chunk_index": 0, "page_number": 1, "text": "First page chunk content."},
        {"chunk_index": 1, "page_number": 2, "text": "Second page chunk content."},
    ]
    embeddings = [[0.01 * i] * 1536 for i in range(1, 3)]

    # Length mismatch
    with pytest.raises(ValueError, match="does not match embeddings count"):
        await repo.save_chunks(sqlite_session, p.id, v.id, chunks_data, [embeddings[0]])

    # Successful persistence
    saved = await repo.save_chunks(sqlite_session, p.id, v.id, chunks_data, embeddings)
    assert len(saved) == 2
    assert saved[0].page_number == 1 and saved[0].chunk_index == 0
    assert saved[1].page_number == 2 and saved[1].chunk_index == 1

    # Query back
    retrieved = await repo.get_chunks_by_version(sqlite_session, v.id)
    assert len(retrieved) == 2
    assert retrieved[0].text == "First page chunk content."
    assert len(retrieved[0].embedding) == 1536


def test_foreign_key_integrity_and_cascade(sqlite_session):
    p = Policy(title="Remote Work", category="HR", region="US")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="/r.pdf", content_hash="h")
    sqlite_session.add(p)
    sqlite_session.add(v)
    sqlite_session.commit()

    chunk = PolicyChunk(policy_id=p.id, policy_version_id=v.id, page_number=1, chunk_index=0, text="Chunk text", char_count=10, embedding=[0.1] * 1536)
    sqlite_session.add(chunk)
    sqlite_session.commit()

    # Cascade delete on policy version removal
    assert sqlite_session.query(PolicyChunk).count() == 1
    sqlite_session.delete(v)
    sqlite_session.commit()
    assert sqlite_session.query(PolicyChunk).count() == 0

    # Foreign key violation
    bad_chunk = PolicyChunk(policy_id=p.id, policy_version_id=uuid.uuid4(), page_number=1, chunk_index=0, text="Bad", char_count=3, embedding=[0.1] * 1536)
    sqlite_session.add(bad_chunk)
    with pytest.raises(IntegrityError):
        sqlite_session.commit()
    sqlite_session.rollback()


def test_migration_003_upgrade_and_downgrade():
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20261019_002_create_policy_chunks.py"
    spec = importlib.util.spec_from_file_location("migration_003", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
        inspector = sa.inspect(conn)
        assert "policy_chunks" in inspector.get_table_names()
        cols = {c["name"] for c in inspector.get_columns("policy_chunks")}
        assert {"id", "policy_id", "policy_version_id", "page_number", "chunk_index", "text", "char_count", "embedding", "created_at"}.issubset(cols)

        with Operations.context(ctx):
            migration.downgrade()
        assert "policy_chunks" not in sa.inspect(conn).get_table_names()
