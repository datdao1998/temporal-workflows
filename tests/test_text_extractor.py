"""Unit tests for the extract_text activity."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import fitz
import pytest

from src.activities.text_extractor import extract_text
from src.models import ExtractionParams, TextResult, PageText


def _create_pdf(pages_text: list[str], path: str) -> str:
    """Create a PDF with the given text on each page."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestExtractText:
    @pytest.mark.asyncio
    async def test_extracts_text_from_simple_pdf(self, tmp_dir):
        path = os.path.join(tmp_dir, "simple.pdf")
        _create_pdf(["Hello world", "Page two content"], path)

        params = ExtractionParams(job_id="test-1", file_path=path)
        result = await extract_text(params)

        assert isinstance(result, TextResult)
        assert len(result.pages) == 2
        assert "Hello world" in result.pages[0].text
        assert "Page two content" in result.pages[1].text
        assert result.pages[0].error is None
        assert result.pages[1].error is None

    @pytest.mark.asyncio
    async def test_page_count_matches(self, tmp_dir):
        path = os.path.join(tmp_dir, "multi.pdf")
        _create_pdf(["A", "B", "C", "D"], path)

        params = ExtractionParams(job_id="test-2", file_path=path)
        result = await extract_text(params)

        assert len(result.pages) == 4
        for i, page in enumerate(result.pages):
            assert page.page_number == i + 1

    @pytest.mark.asyncio
    async def test_empty_pages_return_empty_strings(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.pdf")
        _create_pdf(["", "", ""], path)

        params = ExtractionParams(job_id="test-3", file_path=path)
        result = await extract_text(params)

        assert len(result.pages) == 3
        for page in result.pages:
            assert page.text.strip() == ""
            assert page.error is None

    @pytest.mark.asyncio
    async def test_per_page_error_handling(self, tmp_dir):
        """Simulate a per-page failure and verify it's recorded in PageText.error."""
        path = os.path.join(tmp_dir, "good.pdf")
        _create_pdf(["Page 1", "Page 2", "Page 3"], path)

        params = ExtractionParams(job_id="test-4", file_path=path)

        original_open = fitz.open

        def patched_open(*args, **kwargs):
            doc = original_open(*args, **kwargs)
            original_getitem = doc.__class__.__getitem__

            def failing_getitem(self_doc, idx):
                if idx == 1:  # Make page 2 (index 1) fail
                    raise RuntimeError("simulated page corruption")
                return original_getitem(self_doc, idx)

            doc.__class__.__getitem__ = failing_getitem
            return doc

        with patch("src.activities.text_extractor.fitz.open", side_effect=patched_open):
            result = await extract_text(params)

        assert len(result.pages) == 3
        # Page 1 should succeed
        assert "Page 1" in result.pages[0].text
        assert result.pages[0].error is None
        # Page 2 should have an error
        assert result.pages[1].text == ""
        assert "simulated page corruption" in result.pages[1].error
        # Page 3 should also have the error since we patched __getitem__ on the class
        # but page_number should be correct
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2
        assert result.pages[2].page_number == 3

    @pytest.mark.asyncio
    async def test_single_page_pdf(self, tmp_dir):
        path = os.path.join(tmp_dir, "single.pdf")
        _create_pdf(["Only page"], path)

        params = ExtractionParams(job_id="test-5", file_path=path)
        result = await extract_text(params)

        assert len(result.pages) == 1
        assert "Only page" in result.pages[0].text
        assert result.pages[0].page_number == 1
