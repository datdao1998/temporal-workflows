"""FastAPI application entry point.

Creates the FastAPI app, includes API routes, and sets up
database and Temporal client connections on startup.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from temporalio.client import Client

from src.api.routes import router
from src.db.database import init_db

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost/pdf_extraction"
)

_temporal_client: Client | None = None


async def get_temporal_client() -> Client | None:
    """Return the cached Temporal client, if available."""
    return _temporal_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the FastAPI app."""
    global _temporal_client

    # Initialize database engine
    init_db(DATABASE_URL)

    # Attempt Temporal client connection (non-fatal if unavailable)
    try:
        _temporal_client = await Client.connect(TEMPORAL_HOST)
    except Exception:
        _temporal_client = None

    yield

    _temporal_client = None


app = FastAPI(title="PDF Extraction Service", lifespan=lifespan)
app.include_router(router)
