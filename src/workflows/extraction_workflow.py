"""Temporal workflow for orchestrating PDF extraction."""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.activities.metadata_extractor import extract_metadata
    from src.activities.store_result import store_result
    from src.activities.structured_data_extractor import extract_structured_data
    from src.activities.text_extractor import extract_text
    from src.models import ExtractionParams, ExtractionResult, StoreParams


@workflow.defn
class PDFExtractionWorkflow:
    """Orchestrates parallel PDF extraction and result storage."""

    @workflow.run
    async def run(self, params: ExtractionParams) -> ExtractionResult:
        extractor_retry = RetryPolicy(maximum_attempts=3)
        storage_retry = RetryPolicy(maximum_attempts=5)

        try:
            text_result, metadata_result, structured_result = await asyncio.gather(
                workflow.execute_activity(
                    extract_text,
                    params,
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=extractor_retry,
                ),
                workflow.execute_activity(
                    extract_metadata,
                    params,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=extractor_retry,
                ),
                workflow.execute_activity(
                    extract_structured_data,
                    params,
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=extractor_retry,
                ),
            )

            result = ExtractionResult(
                text=text_result,
                metadata=metadata_result,
                structured_data=structured_result,
            )

            await workflow.execute_activity(
                store_result,
                StoreParams(job_id=params.job_id, result=result),
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=storage_retry,
            )

            return result
        except Exception as e:
            # Mark job as failed by re-raising — Temporal records the error.
            # The API layer / caller can read the workflow failure to set
            # the job status to FAILED with the error message.
            raise
