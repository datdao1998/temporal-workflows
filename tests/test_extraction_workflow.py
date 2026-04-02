"""Unit tests for the PDFExtractionWorkflow.

These tests mock workflow.execute_activity to validate the workflow logic
(parallel execution, result combination, retry policies, error handling)
without requiring a running Temporal server.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from temporalio.common import RetryPolicy

from src.activities.metadata_extractor import extract_metadata
from src.activities.store_result import store_result
from src.activities.structured_data_extractor import extract_structured_data
from src.activities.text_extractor import extract_text
from src.models import (
    ExtractionParams,
    ExtractionResult,
    MetadataResult,
    PageText,
    StoreParams,
    StructuredDataResult,
    Table,
    TableRow,
    TextResult,
)
from src.workflows.extraction_workflow import PDFExtractionWorkflow


def _sample_text_result() -> TextResult:
    return TextResult(pages=[
        PageText(page_number=1, text="Hello world"),
        PageText(page_number=2, text="Page two"),
    ])


def _sample_metadata_result() -> MetadataResult:
    return MetadataResult(
        title="Test",
        author="Author",
        subject=None,
        creation_date="2024-01-01",
        modification_date=None,
        page_count=2,
        file_size=1024,
    )


def _sample_structured_result() -> StructuredDataResult:
    return StructuredDataResult(tables=[
        Table(rows=[TableRow(values=["a", "b"])], page_number=1),
    ])


async def _mock_execute_activity_success(activity_fn, params, **kwargs):
    """Return the appropriate mock result based on which activity is called."""
    if activity_fn is extract_text:
        return _sample_text_result()
    elif activity_fn is extract_metadata:
        return _sample_metadata_result()
    elif activity_fn is extract_structured_data:
        return _sample_structured_result()
    elif activity_fn is store_result:
        return None
    raise ValueError(f"Unexpected activity: {activity_fn}")


def _make_mock_workflow(execute_side_effect):
    """Create a mock workflow module with execute_activity as a coroutine function."""
    mock_wf = MagicMock()
    mock_wf.execute_activity = execute_side_effect
    return mock_wf


class TestPDFExtractionWorkflow:
    @pytest.mark.asyncio
    async def test_successful_extraction_returns_combined_result(self):
        """All three activities succeed and results are combined into ExtractionResult."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-1", file_path="/tmp/test.pdf")

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _mock_execute_activity_success
            result = await wf.run(params)

        assert isinstance(result, ExtractionResult)
        assert len(result.text.pages) == 2
        assert result.text.pages[0].text == "Hello world"
        assert result.metadata.title == "Test"
        assert result.metadata.page_count == 2
        assert len(result.structured_data.tables) == 1

    @pytest.mark.asyncio
    async def test_store_result_called_with_correct_params(self):
        """store_result activity receives the combined result and correct job_id."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-store", file_path="/tmp/test.pdf")

        captured_store_params = []

        async def _capture_store(activity_fn, params_arg, **kwargs):
            if activity_fn is store_result:
                captured_store_params.append(params_arg)
                return None
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _capture_store
            await wf.run(params)

        assert len(captured_store_params) == 1
        sp = captured_store_params[0]
        assert isinstance(sp, StoreParams)
        assert sp.job_id == "job-store"
        assert sp.result.metadata.title == "Test"

    @pytest.mark.asyncio
    async def test_extraction_activities_called_with_correct_params(self):
        """All three extraction activities receive the original ExtractionParams."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-params", file_path="/tmp/check.pdf")

        called_with = []

        async def _track(activity_fn, params_arg, **kwargs):
            called_with.append((activity_fn, params_arg))
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _track
            await wf.run(params)

        extraction_calls = [(fn, p) for fn, p in called_with if fn is not store_result]
        assert len(extraction_calls) == 3
        for fn, p in extraction_calls:
            assert p is params

    @pytest.mark.asyncio
    async def test_retry_policy_3_attempts_for_extractors(self):
        """Extraction activities use retry policy with 3 maximum attempts."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-retry", file_path="/tmp/test.pdf")

        call_kwargs = []

        async def _track_kwargs(activity_fn, params_arg, **kwargs):
            call_kwargs.append((activity_fn, kwargs))
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _track_kwargs
            await wf.run(params)

        for fn, kw in call_kwargs:
            if fn is not store_result:
                assert kw["retry_policy"].maximum_attempts == 3

    @pytest.mark.asyncio
    async def test_retry_policy_5_attempts_for_storage(self):
        """store_result activity uses retry policy with 5 maximum attempts."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-retry-store", file_path="/tmp/test.pdf")

        call_kwargs = []

        async def _track_kwargs(activity_fn, params_arg, **kwargs):
            call_kwargs.append((activity_fn, kwargs))
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _track_kwargs
            await wf.run(params)

        store_kw = [kw for fn, kw in call_kwargs if fn is store_result]
        assert len(store_kw) == 1
        assert store_kw[0]["retry_policy"].maximum_attempts == 5

    @pytest.mark.asyncio
    async def test_activity_failure_propagates(self):
        """When an extraction activity fails, the workflow raises the exception."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-fail", file_path="/tmp/bad.pdf")

        async def _fail_on_text(activity_fn, params_arg, **kwargs):
            if activity_fn is extract_text:
                raise RuntimeError("text extraction failed")
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _fail_on_text
            with pytest.raises(RuntimeError, match="text extraction failed"):
                await wf.run(params)

    @pytest.mark.asyncio
    async def test_result_contains_all_three_components(self):
        """ExtractionResult has text, metadata, and structured_data all populated."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-complete", file_path="/tmp/test.pdf")

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _mock_execute_activity_success
            result = await wf.run(params)

        assert result.text is not None
        assert result.metadata is not None
        assert result.structured_data is not None
        assert result.text.pages[1].text == "Page two"
        assert result.metadata.file_size == 1024
        assert result.structured_data.tables[0].rows[0].values == ["a", "b"]

    @pytest.mark.asyncio
    async def test_four_activity_calls_total(self):
        """Workflow makes exactly 4 activity calls: 3 extractors + 1 store."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-count", file_path="/tmp/test.pdf")

        call_count = []

        async def _count(activity_fn, params_arg, **kwargs):
            call_count.append(activity_fn)
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _count
            await wf.run(params)

        assert len(call_count) == 4

    @pytest.mark.asyncio
    async def test_store_not_called_when_extraction_fails(self):
        """If extraction fails, store_result should not be called."""
        wf = PDFExtractionWorkflow()
        params = ExtractionParams(job_id="job-no-store", file_path="/tmp/bad.pdf")

        called_activities = []

        async def _fail_on_metadata(activity_fn, params_arg, **kwargs):
            called_activities.append(activity_fn)
            if activity_fn is extract_metadata:
                raise RuntimeError("metadata failed")
            return await _mock_execute_activity_success(activity_fn, params_arg, **kwargs)

        with patch("src.workflows.extraction_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = _fail_on_metadata
            with pytest.raises(RuntimeError):
                await wf.run(params)

        assert store_result not in called_activities
