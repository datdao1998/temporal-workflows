"""Unit tests for the store_result Temporal activity."""

import pytest
import pytest_asyncio
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base
from src.db.repository import JobRepository
from src.activities.store_result import store_result
from src.models import (
    ExtractionResult,
    JobStatus,
    MetadataResult,
    PageText,
    StoreParams,
    StructuredDataResult,
    Table,
    TableRow,
    TextResult,
)


@pytest_asyncio.fixture
async def db_setup():
    """Create an in-memory SQLite database and yield engine + session factory."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, session_factory
    await engine.dispose()


def _make_extraction_result() -> ExtractionResult:
    """Build a sample ExtractionResult for testing."""
    return ExtractionResult(
        text=TextResult(pages=[
            PageText(page_number=1, text="Page one content"),
        ]),
        metadata=MetadataResult(
            title="Test Doc",
            author="Tester",
            subject=None,
            creation_date="2024-06-01T00:00:00",
            modification_date=None,
            page_count=1,
            file_size=512,
        ),
        structured_data=StructuredDataResult(tables=[]),
    )


class TestStoreResultActivity:
    @pytest.mark.asyncio
    async def test_store_result_persists_and_completes_job(self, db_setup):
        engine, session_factory = db_setup

        # Create a job first
        async with session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                job = await repo.create_job(file_path="/tmp/test.pdf", job_id="job-123")

        extraction_result = _make_extraction_result()
        params = StoreParams(job_id="job-123", result=extraction_result)

        # Patch get_session_factory to return our test session factory
        with patch("src.activities.store_result.get_session_factory", return_value=session_factory):
            await store_result(params)

        # Verify the job was updated
        async with session_factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job("job-123")

        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.result is not None
        assert job.result.text.pages[0].text == "Page one content"
        assert job.result.metadata.title == "Test Doc"
        assert job.result.metadata.page_count == 1

    @pytest.mark.asyncio
    async def test_store_result_with_structured_data(self, db_setup):
        engine, session_factory = db_setup

        async with session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                await repo.create_job(file_path="/tmp/tables.pdf", job_id="job-456")

        result = ExtractionResult(
            text=TextResult(pages=[PageText(page_number=1, text="data")]),
            metadata=MetadataResult(
                title=None, author=None, subject=None,
                creation_date=None, modification_date=None,
                page_count=1, file_size=256,
            ),
            structured_data=StructuredDataResult(tables=[
                Table(rows=[TableRow(values=["col1", "col2"])], page_number=1),
            ]),
        )
        params = StoreParams(job_id="job-456", result=result)

        with patch("src.activities.store_result.get_session_factory", return_value=session_factory):
            await store_result(params)

        async with session_factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job("job-456")

        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert len(job.result.structured_data.tables) == 1
        assert job.result.structured_data.tables[0].rows[0].values == ["col1", "col2"]

    @pytest.mark.asyncio
    async def test_store_result_with_error_pages(self, db_setup):
        engine, session_factory = db_setup

        async with session_factory() as session:
            async with session.begin():
                repo = JobRepository(session)
                await repo.create_job(file_path="/tmp/errors.pdf", job_id="job-789")

        result = ExtractionResult(
            text=TextResult(pages=[
                PageText(page_number=1, text="ok"),
                PageText(page_number=2, text="", error="corrupt page"),
            ]),
            metadata=MetadataResult(
                title=None, author=None, subject=None,
                creation_date=None, modification_date=None,
                page_count=2, file_size=100,
            ),
            structured_data=StructuredDataResult(tables=[]),
        )
        params = StoreParams(job_id="job-789", result=result)

        with patch("src.activities.store_result.get_session_factory", return_value=session_factory):
            await store_result(params)

        async with session_factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job("job-789")

        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.result.text.pages[1].error == "corrupt page"
