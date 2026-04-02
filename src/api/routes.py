"""API routes for PDF extraction service."""

import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from temporalio.client import Client

from src.api.validation import FileTooLargeError, PDFValidationError, validate_pdf
from src.db.database import get_session_factory
from src.db.repository import JobRepository
from src.models import ExtractionParams, JobStatus, to_dict

router = APIRouter()

# Directory for storing uploaded PDFs
UPLOAD_DIR = os.environ.get("PDF_UPLOAD_DIR", "uploads")

# Temporal connection settings
TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = "pdf-extraction"


async def _get_temporal_client() -> Client:
    """Get a connected Temporal client."""
    return await Client.connect(TEMPORAL_HOST)


@router.post("/jobs")
async def create_job(file: UploadFile):
    """Accept a PDF upload, validate, save, start workflow, return job ID."""
    content = await file.read()

    # Validate PDF
    try:
        validate_pdf(content)
    except PDFValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=e.message)

    job_id = str(uuid.uuid4())

    # Save file to storage
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(content)

    # Create job record in database
    session_factory = get_session_factory()
    async with session_factory() as session:
        async with session.begin():
            repo = JobRepository(session)
            await repo.create_job(file_path=file_path, job_id=job_id)

    # Start Temporal workflow
    try:
        client = await _get_temporal_client()
        await client.start_workflow(
            "PDFExtractionWorkflow",
            ExtractionParams(job_id=job_id, file_path=file_path),
            id=f"pdf-extraction-{job_id}",
            task_queue=TASK_QUEUE,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to start extraction workflow")

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Query job status and return result/error based on state."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        async with session.begin():
            repo = JobRepository(session)
            job = await repo.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    response = {"job_id": job.id, "status": job.status.value}

    if job.status == JobStatus.COMPLETED and job.result is not None:
        response["result"] = to_dict(job.result)
    elif job.status == JobStatus.FAILED and job.error is not None:
        response["error"] = job.error

    return response
