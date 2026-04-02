# PDF Extraction Service

A Temporal-orchestrated PDF information extraction system. Accepts PDF files via a FastAPI API, extracts text, metadata, and structured data (tables), and persists results to PostgreSQL.

## Architecture

- **FastAPI API Server** — accepts PDF uploads, starts Temporal workflows, serves extraction results
- **Temporal Workflow** — orchestrates three extraction activities in parallel with configurable retry policies
- **Activities** — text extraction (PyMuPDF), metadata extraction (PyMuPDF), structured data/table extraction (pdfplumber)
- **PostgreSQL** — stores job state and extraction results as JSON

## Prerequisites

- Python 3.10+
- PostgreSQL
- [Temporal Server](https://docs.temporal.io/cli#install)

## Installation

```bash
pip install -r requirements.txt
```

## Database Setup

Create the database:

```sql
CREATE DATABASE pdf_extraction;
```

The app defaults to `postgresql+asyncpg://localhost/pdf_extraction`. Override with an environment variable:

```bash
set DATABASE_URL=postgresql+asyncpg://user:password@localhost/pdf_extraction
```

## Running the Service

### 1. Start Temporal Server

```bash
temporal server start-dev
```

Starts a local dev server on `localhost:7233`. Override with `TEMPORAL_HOST` env var if needed.

### 2. Start the Temporal Worker

```bash
python -m src.worker
```

Registers the workflow and activities, polls the `pdf-extraction` task queue.

### 3. Start the API Server

```bash
uvicorn src.main:app --reload
```

API available at `http://localhost:8000`.

## API Usage

### Submit a PDF

```bash
curl -X POST http://localhost:8000/jobs -F "file=@your-document.pdf"
```

Response:
```json
{ "job_id": "uuid-here", "status": "pending" }
```

### Check Job Status

```bash
curl http://localhost:8000/jobs/{job_id}
```

Response varies by status:
- **pending/running** — `{ "job_id": "...", "status": "pending" }`
- **completed** — `{ "job_id": "...", "status": "completed", "result": { ... } }`
- **failed** — `{ "job_id": "...", "status": "failed", "error": "..." }`

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://localhost/pdf_extraction` | Database connection string |
| `TEMPORAL_HOST` | `localhost:7233` | Temporal server address |
| `PDF_UPLOAD_DIR` | `uploads` | Directory for uploaded PDF files |

## Running Tests

Tests use in-memory SQLite and mocked Temporal — no external services needed:

```bash
python -m pytest tests/ -v
```

## Project Structure

```
src/
├── api/
│   ├── routes.py          # FastAPI endpoints (POST /jobs, GET /jobs/{id})
│   └── validation.py      # PDF validation (magic bytes, file size)
├── activities/
│   ├── text_extractor.py          # Text extraction activity
│   ├── metadata_extractor.py      # Metadata extraction activity
│   ├── structured_data_extractor.py  # Table extraction activity
│   └── store_result.py            # Result persistence activity
├── workflows/
│   └── extraction_workflow.py     # PDFExtractionWorkflow
├── models/
│   └── schemas.py         # Data models and serialization
├── db/
│   ├── database.py        # Engine and session factory
│   ├── models.py          # SQLAlchemy ORM model
│   └── repository.py      # JobRepository
├── main.py                # FastAPI app entry point
└── worker.py              # Temporal worker entry point
tests/
└── ...                    # Unit and property-based tests
```
