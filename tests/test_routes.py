"""Unit tests for API routes."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.routes import router
from src.db.models import Base
from src.db.repository import JobRepository
from src.models import (
    ExtractionResult,
    JobStatus,
    MetadataResult,
    PageText,
    StructuredDataResult,
    Table,
    TableRow,
    TextResult,
)

# Minimal valid PDF bytes (header + minimal structure)
VALID_PDF_BYTES = b"%PDF-1.4 minimal"


@pytest_asyncio.fixture
async def db_session_factory():
    """Create an in-memory SQLite database and return a session factory."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session_factory, tmp_path):
    """Create a test HTTP client with mocked DB and Temporal."""
    app = FastAPI()
    app.include_router(router)

    with (
        patch("src.api.routes.get_session_factory", return_value=db_session_factory),
        patch("src.api.routes.UPLOAD_DIR", str(tmp_path)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def _make_extraction_result() -> ExtractionResult:
    """Build a sample ExtractionResult for testing."""
    return ExtractionResult(
        text=TextResult(pages=[PageText(page_number=1, text="Hello")]),
        metadata=MetadataResult(
            title="T", author=None, subject=None,
            creation_date=None, modification_date=None,
            page_count=1, file_size=100,
        ),
        structured_data=StructuredDataResult(tables=[]),
    )


class TestPostJobs:
    @pytest.mark.asyncio
    async def test_valid_pdf_returns_job_id(self, client, db_session_factory):
        """POST /jobs with a valid PDF returns 200 with job_id and pending status."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()

        with patch("src.api.routes._get_temporal_client", return_value=mock_temporal):
            resp = await client.post(
                "/jobs",
                files={"file": ("test.pdf", VALID_PDF_BYTES, "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        # Verify it's a valid UUID
        uuid.UUID(data["job_id"])

    @pytest.mark.asyncio
    async def test_valid_pdf_creates_db_record(self, client, db_session_factory):
        """POST /jobs creates a job record in the database."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()

        with patch("src.api.routes._get_temporal_client", return_value=mock_temporal):
            resp = await client.post(
                "/jobs",
                files={"file": ("test.pdf", VALID_PDF_BYTES, "application/pdf")},
            )

        job_id = resp.json()["job_id"]
        async with db_session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_valid_pdf_starts_temporal_workflow(self, client, db_session_factory):
        """POST /jobs starts a Temporal workflow."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()

        with patch("src.api.routes._get_temporal_client", return_value=mock_temporal):
            resp = await client.post(
                "/jobs",
                files={"file": ("test.pdf", VALID_PDF_BYTES, "application/pdf")},
            )

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_called_once()
        call_kwargs = mock_temporal.start_workflow.call_args
        assert call_kwargs[0][0] == "PDFExtractionWorkflow"
        assert call_kwargs[1]["task_queue"] == "pdf-extraction"

    @pytest.mark.asyncio
    async def test_invalid_pdf_returns_400(self, client):
        """POST /jobs with non-PDF bytes returns 400."""
        resp = await client.post(
            "/jobs",
            files={"file": ("bad.txt", b"not a pdf", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_file_too_large_returns_413(self, client):
        """POST /jobs with oversized file returns 413."""
        with patch("src.api.routes.validate_pdf", side_effect=__import__("src.api.validation", fromlist=["FileTooLargeError"]).FileTooLargeError("Too big", max_size=50 * 1024 * 1024)):
            resp = await client.post(
                "/jobs",
                files={"file": ("big.pdf", b"%PDF-big", "application/pdf")},
            )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_temporal_failure_returns_500(self, client, db_session_factory):
        """POST /jobs returns 500 if Temporal workflow start fails."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("src.api.routes._get_temporal_client", return_value=mock_temporal):
            resp = await client.post(
                "/jobs",
                files={"file": ("test.pdf", VALID_PDF_BYTES, "application/pdf")},
            )

        assert resp.status_code == 500
        assert "workflow" in resp.json()["detail"].lower()


class TestGetJob:
    @pytest.mark.asyncio
    async def test_pending_job(self, client, db_session_factory):
        """GET /jobs/{id} for a pending job returns status only."""
        async with db_session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.create_job(file_path="/tmp/test.pdf")
                job_id = job.id

        with patch("src.api.routes.get_session_factory", return_value=db_session_factory):
            resp = await client.get(f"/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "pending"
        assert "result" not in data
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_completed_job_includes_result(self, client, db_session_factory):
        """GET /jobs/{id} for a completed job includes the result."""
        result = _make_extraction_result()
        async with db_session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.create_job(file_path="/tmp/test.pdf")
                await repo.store_result(job.id, result)
                job_id = job.id

        with patch("src.api.routes.get_session_factory", return_value=db_session_factory):
            resp = await client.get(f"/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert "result" in data
        assert data["result"]["metadata"]["title"] == "T"

    @pytest.mark.asyncio
    async def test_failed_job_includes_error(self, client, db_session_factory):
        """GET /jobs/{id} for a failed job includes the error message."""
        async with db_session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.create_job(file_path="/tmp/test.pdf")
                await repo.update_job_status(job.id, JobStatus.FAILED, error="extraction crashed")
                job_id = job.id

        with patch("src.api.routes.get_session_factory", return_value=db_session_factory):
            resp = await client.get(f"/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"] == "extraction crashed"

    @pytest.mark.asyncio
    async def test_unknown_job_returns_404(self, client, db_session_factory):
        """GET /jobs/{id} for a non-existent job returns 404."""
        with patch("src.api.routes.get_session_factory", return_value=db_session_factory):
            resp = await client.get(f"/jobs/{uuid.uuid4()}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_running_job(self, client, db_session_factory):
        """GET /jobs/{id} for a running job returns status without result or error."""
        async with db_session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.create_job(file_path="/tmp/test.pdf")
                await repo.update_job_status(job.id, JobStatus.RUNNING)
                job_id = job.id

        with patch("src.api.routes.get_session_factory", return_value=db_session_factory):
            resp = await client.get(f"/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "result" not in data
        assert "error" not in data
