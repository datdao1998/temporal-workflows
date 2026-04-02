"""Unit tests for JobRepository using an in-memory SQLite database."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database and yield an async session."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _make_extraction_result() -> ExtractionResult:
    """Build a sample ExtractionResult for testing."""
    return ExtractionResult(
        text=TextResult(pages=[
            PageText(page_number=1, text="Hello world"),
            PageText(page_number=2, text="", error="corrupt"),
        ]),
        metadata=MetadataResult(
            title="Test",
            author="Author",
            subject=None,
            creation_date="2024-01-01T00:00:00",
            modification_date=None,
            page_count=2,
            file_size=1024,
        ),
        structured_data=StructuredDataResult(tables=[
            Table(rows=[TableRow(values=["a", "b"])], page_number=1),
        ]),
    )


class TestJobRepository:
    @pytest.mark.asyncio
    async def test_create_job(self, async_session: AsyncSession):
        repo = JobRepository(async_session)
        job = await repo.create_job(file_path="/tmp/test.pdf")

        assert job.id is not None
        assert len(job.id) > 0
        assert job.status == JobStatus.PENDING
        assert job.file_path == "/tmp/test.pdf"
        assert job.result is None
        assert job.error is None

    @pytest.mark.asyncio
    async def test_get_job(self, async_session: AsyncSession):
        repo = JobRepository(async_session)
        created = await repo.create_job(file_path="/tmp/test.pdf")

        fetched = await repo.get_job(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.status == JobStatus.PENDING
        assert fetched.file_path == "/tmp/test.pdf"

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_unknown_id(self, async_session: AsyncSession):
        repo = JobRepository(async_session)

        result = await repo.get_job("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_job_status(self, async_session: AsyncSession):
        repo = JobRepository(async_session)
        created = await repo.create_job(file_path="/tmp/test.pdf")

        updated = await repo.update_job_status(created.id, JobStatus.RUNNING)

        assert updated is not None
        assert updated.status == JobStatus.RUNNING

        # Verify via fresh get
        fetched = await repo.get_job(created.id)
        assert fetched is not None
        assert fetched.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_job_status_with_error(self, async_session: AsyncSession):
        repo = JobRepository(async_session)
        created = await repo.create_job(file_path="/tmp/test.pdf")

        updated = await repo.update_job_status(created.id, JobStatus.FAILED, error="something broke")

        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error == "something broke"

    @pytest.mark.asyncio
    async def test_store_result(self, async_session: AsyncSession):
        repo = JobRepository(async_session)
        created = await repo.create_job(file_path="/tmp/test.pdf")
        extraction_result = _make_extraction_result()

        updated = await repo.store_result(created.id, extraction_result)

        assert updated is not None
        assert updated.status == JobStatus.COMPLETED
        assert updated.result is not None
        assert updated.result.text.pages[0].text == "Hello world"
        assert updated.result.text.pages[1].error == "corrupt"
        assert updated.result.metadata.title == "Test"
        assert updated.result.metadata.subject is None
        assert updated.result.metadata.page_count == 2
        assert updated.result.structured_data.tables[0].rows[0].values == ["a", "b"]

        # Verify round-trip via fresh get
        fetched = await repo.get_job(created.id)
        assert fetched is not None
        assert fetched.status == JobStatus.COMPLETED
        assert fetched.result is not None
        assert fetched.result.metadata.file_size == 1024
