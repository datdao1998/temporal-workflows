"""Unit tests for the extract_metadata activity."""

import os
import tempfile

import fitz
import pytest

from src.activities.metadata_extractor import extract_metadata
from src.models import ExtractionParams, MetadataResult


def _create_pdf(path: str, num_pages: int = 1, metadata: dict | None = None) -> str:
    """Create a PDF with optional metadata and page count."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    if metadata:
        doc.set_metadata(metadata)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestExtractMetadata:
    @pytest.mark.asyncio
    async def test_extracts_known_metadata_fields(self, tmp_dir):
        path = os.path.join(tmp_dir, "with_meta.pdf")
        _create_pdf(path, num_pages=2, metadata={
            "title": "Test Title",
            "author": "Test Author",
            "subject": "Test Subject",
        })

        params = ExtractionParams(job_id="meta-1", file_path=path)
        result = await extract_metadata(params)

        assert isinstance(result, MetadataResult)
        assert result.title == "Test Title"
        assert result.author == "Test Author"
        assert result.subject == "Test Subject"

    @pytest.mark.asyncio
    async def test_page_count_matches_actual_pages(self, tmp_dir):
        for num_pages in [1, 3, 7]:
            path = os.path.join(tmp_dir, f"pages_{num_pages}.pdf")
            _create_pdf(path, num_pages=num_pages)

            params = ExtractionParams(job_id=f"meta-pages-{num_pages}", file_path=path)
            result = await extract_metadata(params)

            assert result.page_count == num_pages

    @pytest.mark.asyncio
    async def test_file_size_matches_actual_size(self, tmp_dir):
        path = os.path.join(tmp_dir, "size_check.pdf")
        _create_pdf(path, num_pages=2)

        expected_size = os.path.getsize(path)
        params = ExtractionParams(job_id="meta-size", file_path=path)
        result = await extract_metadata(params)

        assert result.file_size == expected_size

    @pytest.mark.asyncio
    async def test_missing_metadata_fields_return_none(self, tmp_dir):
        path = os.path.join(tmp_dir, "no_meta.pdf")
        _create_pdf(path, num_pages=1)

        params = ExtractionParams(job_id="meta-none", file_path=path)
        result = await extract_metadata(params)

        assert result.title is None
        assert result.author is None
        assert result.subject is None
        # page_count and file_size should still be populated
        assert result.page_count == 1
        assert result.file_size > 0
