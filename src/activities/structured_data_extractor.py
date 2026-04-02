"""Structured data extraction activity for PDF processing."""

import pdfplumber
from temporalio import activity

from src.models import ExtractionParams, StructuredDataResult, Table, TableRow


def merge_spanning_tables(tables: list[Table]) -> list[Table]:
    """Merge consecutive tables that have the same column count.

    Uses a column-count heuristic: if two consecutive tables have the same
    number of columns, they are assumed to be parts of a single table
    spanning multiple pages. The merged table keeps the page_number of the
    first table in the group.
    """
    if not tables:
        return []

    merged: list[Table] = []
    current = tables[0]

    for next_table in tables[1:]:
        current_col_count = len(current.rows[0].values) if current.rows else 0
        next_col_count = len(next_table.rows[0].values) if next_table.rows else 0

        if current_col_count == next_col_count and current_col_count > 0:
            # Merge: append next_table's rows into current
            current = Table(
                rows=current.rows + next_table.rows,
                page_number=current.page_number,
            )
        else:
            merged.append(current)
            current = next_table

    merged.append(current)
    return merged


@activity.defn
async def extract_structured_data(params: ExtractionParams) -> StructuredDataResult:
    """Extract structured table data from a PDF.

    Uses pdfplumber for table detection. Tables spanning multiple pages
    are merged using a column-count matching heuristic.
    """
    tables: list[Table] = []
    with pdfplumber.open(params.file_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for table_data in page_tables:
                rows = [TableRow(values=row) for row in table_data if row]
                if rows:
                    tables.append(Table(rows=rows, page_number=page.page_number))
    merged_tables = merge_spanning_tables(tables)
    return StructuredDataResult(tables=merged_tables)
