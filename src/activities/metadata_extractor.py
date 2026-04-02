"""Metadata extraction activity for PDF processing."""

import os

import fitz
from temporalio import activity

from src.models import ExtractionParams, MetadataResult


@activity.defn
async def extract_metadata(params: ExtractionParams) -> MetadataResult:
    """Extract metadata from a PDF file.

    Reads document metadata fields via PyMuPDF, returning None for any
    missing fields. Always includes page count and file size.
    """
    doc = fitz.open(params.file_path)
    meta = doc.metadata
    result = MetadataResult(
        title=meta.get("title") or None,
        author=meta.get("author") or None,
        subject=meta.get("subject") or None,
        creation_date=meta.get("creationDate") or None,
        modification_date=meta.get("modDate") or None,
        page_count=len(doc),
        file_size=os.path.getsize(params.file_path),
    )
    doc.close()
    return result
