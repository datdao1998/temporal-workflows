"""Text extraction activity for PDF processing."""

import fitz
from temporalio import activity

from src.models import ExtractionParams, PageText, TextResult


@activity.defn
async def extract_text(params: ExtractionParams) -> TextResult:
    """Extract text content from each page of a PDF.

    Per-page failures are caught and recorded in PageText.error
    without halting extraction of remaining pages.
    """
    pages: list[PageText] = []
    doc = fitz.open(params.file_path)
    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            text = page.get_text()
            pages.append(PageText(page_number=page_num + 1, text=text))
        except Exception as e:
            pages.append(PageText(page_number=page_num + 1, text="", error=str(e)))
    doc.close()
    return TextResult(pages=pages)
