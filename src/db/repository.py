"""Job repository for database operations."""

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import JobRow
from src.models import ExtractionResult, Job, JobStatus, from_dict, to_dict


class JobRepository:
    """Async repository for Job CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_job(self, file_path: str, job_id: str | None = None) -> Job:
        """Create a new job record and return it as a domain Job."""
        row = JobRow(
            id=job_id or str(uuid.uuid4()),
            status=JobStatus.PENDING.value,
            file_path=file_path,
        )
        self._session.add(row)
        await self._session.flush()
        return self._row_to_job(row)

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID. Returns None if not found."""
        stmt = select(JobRow).where(JobRow.id == job_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._row_to_job(row)

    async def update_job_status(self, job_id: str, status: JobStatus, error: str | None = None) -> Optional[Job]:
        """Update a job's status (and optionally error). Returns the updated Job or None."""
        stmt = select(JobRow).where(JobRow.id == job_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.status = status.value
        row.updated_at = datetime.now(UTC)
        if error is not None:
            row.error = error
        await self._session.flush()
        return self._row_to_job(row)

    async def store_result(self, job_id: str, extraction_result: ExtractionResult) -> Optional[Job]:
        """Store an ExtractionResult and mark the job as completed."""
        stmt = select(JobRow).where(JobRow.id == job_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.result = to_dict(extraction_result)
        row.status = JobStatus.COMPLETED.value
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return self._row_to_job(row)

    @staticmethod
    def _row_to_job(row: JobRow) -> Job:
        """Convert a SQLAlchemy JobRow to a domain Job dataclass."""
        result = None
        if row.result is not None:
            result = from_dict(ExtractionResult, row.result)
        return Job(
            id=row.id,
            status=JobStatus(row.status),
            file_path=row.file_path,
            result=result,
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
