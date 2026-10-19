"""Integration and failure tests for policy processing workflow."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch
import uuid
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import pymupdf
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from app.auth import AuthenticatedUser, ProfileInfo, UserInfo, get_current_user
from app.config import get_settings
from app.db.models import Base, Policy, PolicyChunk, PolicyVersion, UserRole
from app.db.repository import policy_chunk_repo
from app.errors import AppError
from app.extractor import pdf_extractor
from app.main import create_app
from app.policies import get_db_session
from app.workflow import PolicyProcessingWorkflow


@pytest.fixture
def sqlite_session():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as conn: conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(sa.text("PRAGMA foreign_keys=ON;"))
        yield session
    Base.metadata.drop_all(engine)


def make_test_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), "First page content for the security policy.")
    doc.new_page().insert_text((50, 72), "Second page content for the security policy.")
    data = doc.tobytes()
    doc.close()
    return data


def make_user(role: str = UserRole.HR_ADMINISTRATOR.value) -> AuthenticatedUser:
    uid = uuid.uuid4()
    return AuthenticatedUser(user=UserInfo(id=uid, email="hr@test.com"), profile=ProfileInfo(id=uuid.uuid4(), user_id=uid, role=role, region="GLOBAL", is_hr_administrator=(role == UserRole.HR_ADMINISTRATOR.value)))


@pytest.mark.asyncio
async def test_workflow_success_and_metadata_preservation(sqlite_session):
    p = Policy(title="Security Policy", category="IT", region="GLOBAL")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="policies/sec.pdf", content_hash="hash1")
    sqlite_session.add_all([p, v])
    sqlite_session.commit()

    mock_embed = AsyncMock(return_value=[[0.01] * 768, [0.02] * 768])
    workflow = PolicyProcessingWorkflow(extractor=pdf_extractor, embedder=AsyncMock(embed_chunks=mock_embed), repo=policy_chunk_repo)
    res = await workflow.process_version(sqlite_session, v.id, pdf_bytes=make_test_pdf())

    assert res["processing_status"] == "completed" and res["lifecycle_status"] == "draft" and res["chunks_count"] == 2
    sqlite_session.refresh(v)
    assert v.processing_status == "completed" and v.processing_error is None and v.status == "draft"
    chunks = sqlite_session.query(PolicyChunk).filter_by(policy_version_id=v.id).order_by(PolicyChunk.chunk_index).all()
    assert len(chunks) == 2 and chunks[0].page_number == 1 and chunks[1].page_number == 2 and len(chunks[0].embedding) == 768


@pytest.mark.asyncio
async def test_workflow_retry_is_safe_and_idempotent(sqlite_session):
    p = Policy(title="Safety Policy", category="HR", region="US")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="policies/safety.pdf", content_hash="hash2")
    sqlite_session.add_all([p, v])
    sqlite_session.commit()

    mock_embed = AsyncMock(return_value=[[0.05] * 768, [0.06] * 768])
    workflow = PolicyProcessingWorkflow(extractor=pdf_extractor, embedder=AsyncMock(embed_chunks=mock_embed), repo=policy_chunk_repo)
    await workflow.process_version(sqlite_session, v.id, pdf_bytes=make_test_pdf())
    assert sqlite_session.query(PolicyChunk).filter_by(policy_version_id=v.id).count() == 2

    res2 = await workflow.process_version(sqlite_session, v.id, pdf_bytes=make_test_pdf())
    assert res2["processing_status"] == "completed"
    assert sqlite_session.query(PolicyChunk).filter_by(policy_version_id=v.id).count() == 2


@pytest.mark.asyncio
async def test_workflow_extraction_failure_records_failed_state(sqlite_session):
    p = Policy(title="Corrupt Doc", category="General", region="GLOBAL")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="policies/bad.pdf", content_hash="hash3")
    sqlite_session.add_all([p, v])
    sqlite_session.commit()

    workflow = PolicyProcessingWorkflow(extractor=pdf_extractor, embedder=AsyncMock(), repo=policy_chunk_repo)
    with pytest.raises(AppError) as exc_info:
        await workflow.process_version(sqlite_session, v.id, pdf_bytes=b"corrupted invalid pdf data")

    assert exc_info.value.code == "EXTRACTION_FAILED"
    sqlite_session.refresh(v)
    assert v.processing_status == "failed" and "Extraction failed" in (v.processing_error or "")
    assert sqlite_session.query(PolicyChunk).filter_by(policy_version_id=v.id).count() == 0


@pytest.mark.asyncio
async def test_workflow_embedding_failure_records_failed_state(sqlite_session):
    p = Policy(title="Timeout Doc", category="General", region="GLOBAL")
    v = PolicyVersion(policy_id=p.id, version_label="1.0", storage_path="policies/timeout.pdf", content_hash="hash4")
    sqlite_session.add_all([p, v])
    sqlite_session.commit()

    fail_embedder = AsyncMock(embed_chunks=AsyncMock(side_effect=AppError("Provider timeout", 504, "EMBEDDING_PROVIDER_TIMEOUT")))
    workflow = PolicyProcessingWorkflow(extractor=pdf_extractor, embedder=fail_embedder, repo=policy_chunk_repo)

    with pytest.raises(AppError) as exc_info:
        await workflow.process_version(sqlite_session, v.id, pdf_bytes=make_test_pdf())

    assert exc_info.value.code == "EMBEDDING_PROVIDER_TIMEOUT"
    sqlite_session.refresh(v)
    assert v.processing_status == "failed" and "Provider timeout" in (v.processing_error or "")
    assert sqlite_session.query(PolicyChunk).filter_by(policy_version_id=v.id).count() == 0


def test_process_endpoint_authorization(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    get_settings.cache_clear()
    app, pid, vid = create_app(), uuid.uuid4(), uuid.uuid4()
    client = TestClient(app)

    assert client.post(f"/api/v1/policies/{pid}/versions/{vid}/process").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.EMPLOYEE.value)
    assert TestClient(app).post(f"/api/v1/policies/{pid}/versions/{vid}/process").status_code == 403

    app.dependency_overrides[get_current_user] = lambda: make_user(UserRole.HR_ADMINISTRATOR.value)
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    with patch("app.policies.policy_processing_workflow.process_version", new=AsyncMock(return_value={"processing_status": "completed", "chunks_count": 2})):
        res = TestClient(app).post(f"/api/v1/policies/{pid}/versions/{vid}/process")
        assert res.status_code == 200 and res.json()["processing_status"] == "completed"

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_migration_003_upgrade_and_downgrade():
    migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20261019_003_add_processing_status.py"
    spec = importlib.util.spec_from_file_location("migration_003_ps", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE policy_versions (id TEXT PRIMARY KEY, version_label TEXT);"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx): migration.upgrade()
        cols = {c["name"] for c in sa.inspect(conn).get_columns("policy_versions")}
        assert "processing_status" in cols and "processing_error" in cols
        with Operations.context(ctx): migration.downgrade()
        assert "processing_status" not in {c["name"] for c in sa.inspect(conn).get_columns("policy_versions")}
