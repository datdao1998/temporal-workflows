"""Temporal worker for the PDF extraction system.

Registers the PDFExtractionWorkflow and all extraction activities,
then polls the 'pdf-extraction' task queue.
"""

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from src.activities import (
    extract_metadata,
    extract_structured_data,
    extract_text,
    store_result,
)
from src.db.database import init_db
from src.workflows import PDFExtractionWorkflow

TASK_QUEUE = "pdf-extraction"
TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost/pdf_extraction"
)


async def run_worker(client: Client | None = None) -> None:
    """Start the Temporal worker.

    Args:
        client: Optional pre-connected Temporal client. If not provided,
                connects to TEMPORAL_HOST.
    """
    # Initialize database so activities like store_result can use it
    init_db(DATABASE_URL)

    if client is None:
        client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[PDFExtractionWorkflow],
        activities=[extract_text, extract_metadata, extract_structured_data, store_result],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
