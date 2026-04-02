"""Store result activity for persisting extraction results to the database."""

from temporalio import activity

from src.db.database import get_session_factory
from src.db.repository import JobRepository
from src.models import StoreParams


@activity.defn
async def store_result(params: StoreParams) -> None:
    """Persist an ExtractionResult to the database and mark the job as completed.

    Uses the JobRepository to store the result and update the job status
    to 'completed'. The session is committed within this activity.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        async with session.begin():
            repo = JobRepository(session)
            await repo.store_result(params.job_id, params.result)
