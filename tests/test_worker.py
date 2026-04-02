"""Unit tests for the Temporal worker configuration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.activities import (
    extract_metadata,
    extract_structured_data,
    extract_text,
    store_result,
)
from src.worker import TASK_QUEUE, run_worker
from src.workflows import PDFExtractionWorkflow


class TestWorkerConfiguration:
    def test_task_queue_name(self):
        """Task queue is configured as 'pdf-extraction'."""
        assert TASK_QUEUE == "pdf-extraction"

    @pytest.mark.asyncio
    async def test_worker_registers_correct_workflow(self):
        """Worker registers PDFExtractionWorkflow."""
        mock_client = MagicMock()
        captured = {}

        with patch("src.worker.Worker") as MockWorker:
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=mock_client)

            call_kwargs = MockWorker.call_args
            assert PDFExtractionWorkflow in call_kwargs.kwargs.get(
                "workflows", call_kwargs[1].get("workflows", [])
            ) or PDFExtractionWorkflow in call_kwargs[0][2] if len(call_kwargs[0]) > 2 else True

            # More direct check via keyword args
            _, kwargs = MockWorker.call_args
            assert kwargs["workflows"] == [PDFExtractionWorkflow]

    @pytest.mark.asyncio
    async def test_worker_registers_all_activities(self):
        """Worker registers all four extraction activities."""
        mock_client = MagicMock()

        with patch("src.worker.Worker") as MockWorker:
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=mock_client)

            _, kwargs = MockWorker.call_args
            registered = kwargs["activities"]
            assert extract_text in registered
            assert extract_metadata in registered
            assert extract_structured_data in registered
            assert store_result in registered
            assert len(registered) == 4

    @pytest.mark.asyncio
    async def test_worker_uses_correct_task_queue(self):
        """Worker uses the 'pdf-extraction' task queue."""
        mock_client = MagicMock()

        with patch("src.worker.Worker") as MockWorker:
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=mock_client)

            _, kwargs = MockWorker.call_args
            assert kwargs["task_queue"] == "pdf-extraction"

    @pytest.mark.asyncio
    async def test_worker_passes_client(self):
        """Worker is constructed with the provided Temporal client."""
        mock_client = MagicMock()

        with patch("src.worker.Worker") as MockWorker:
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=mock_client)

            args, _ = MockWorker.call_args
            assert args[0] is mock_client

    @pytest.mark.asyncio
    async def test_worker_calls_run(self):
        """Worker.run() is awaited to start polling."""
        mock_client = MagicMock()

        with patch("src.worker.Worker") as MockWorker:
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=mock_client)

            instance.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_worker_connects_to_default_when_no_client(self):
        """When no client is provided, connects to localhost:7233."""
        mock_client = MagicMock()

        with patch("src.worker.Client") as MockClient, \
             patch("src.worker.Worker") as MockWorker:
            MockClient.connect = AsyncMock(return_value=mock_client)
            instance = MagicMock()
            instance.run = AsyncMock()
            MockWorker.return_value = instance

            await run_worker(client=None)

            MockClient.connect.assert_awaited_once_with("localhost:7233")
            args, _ = MockWorker.call_args
            assert args[0] is mock_client
