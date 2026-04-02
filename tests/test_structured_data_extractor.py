"""Unit tests for the extract_structured_data activity and merge_spanning_tables."""

import os
import tempfile

import pdfplumber
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table as RLTable, TableStyle

from src.activities.structured_data_extractor import (
    extract_structured_data,
    merge_spanning_tables,
)
from src.models import ExtractionParams, StructuredDataResult, Table, TableRow


# --- Helper ---

def _create_pdf_with_table(path: str, table_data: list[list[str]]) -> str:
    """Create a simple PDF containing one table."""
    doc = SimpleDocTemplate(path, pagesize=letter)
    rl_table = RLTable(table_data)
    rl_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, "black"),
    ]))
    doc.build([rl_table])
    return path


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# --- merge_spanning_tables tests ---

class TestMergeSpanningTables:
    def test_empty_list_returns_empty(self):
        assert merge_spanning_tables([]) == []

    def test_single_table_returned_as_is(self):
        table = Table(
            rows=[TableRow(values=["a", "b"]), TableRow(values=["c", "d"])],
            page_number=1,
        )
        result = merge_spanning_tables([table])
        assert len(result) == 1
        assert result[0].rows == table.rows
        assert result[0].page_number == 1

    def test_merges_consecutive_same_column_count(self):
        t1 = Table(
            rows=[TableRow(values=["a", "b"])],
            page_number=1,
        )
        t2 = Table(
            rows=[TableRow(values=["c", "d"])],
            page_number=2,
        )
        result = merge_spanning_tables([t1, t2])
        assert len(result) == 1
        assert len(result[0].rows) == 2
        assert result[0].page_number == 1
        assert result[0].rows[0].values == ["a", "b"]
        assert result[0].rows[1].values == ["c", "d"]

    def test_does_not_merge_different_column_counts(self):
        t1 = Table(
            rows=[TableRow(values=["a", "b"])],
            page_number=1,
        )
        t2 = Table(
            rows=[TableRow(values=["x", "y", "z"])],
            page_number=2,
        )
        result = merge_spanning_tables([t1, t2])
        assert len(result) == 2
        assert result[0].page_number == 1
        assert result[1].page_number == 2

    def test_merges_three_consecutive_same_columns(self):
        tables = [
            Table(rows=[TableRow(values=["a", "b"])], page_number=1),
            Table(rows=[TableRow(values=["c", "d"])], page_number=2),
            Table(rows=[TableRow(values=["e", "f"])], page_number=3),
        ]
        result = merge_spanning_tables(tables)
        assert len(result) == 1
        assert len(result[0].rows) == 3
        assert result[0].page_number == 1

    def test_mixed_merge_and_separate(self):
        """Two 2-col tables then a 3-col table: first two merge, third stays separate."""
        tables = [
            Table(rows=[TableRow(values=["a", "b"])], page_number=1),
            Table(rows=[TableRow(values=["c", "d"])], page_number=2),
            Table(rows=[TableRow(values=["x", "y", "z"])], page_number=3),
        ]
        result = merge_spanning_tables(tables)
        assert len(result) == 2
        assert len(result[0].rows) == 2
        assert result[0].page_number == 1
        assert len(result[1].rows) == 1
        assert result[1].page_number == 3

    def test_preserves_total_row_count(self):
        tables = [
            Table(rows=[TableRow(values=["a", "b"]), TableRow(values=["c", "d"])], page_number=1),
            Table(rows=[TableRow(values=["e", "f"])], page_number=2),
        ]
        result = merge_spanning_tables(tables)
        total_input_rows = sum(len(t.rows) for t in tables)
        total_output_rows = sum(len(t.rows) for t in result)
        assert total_input_rows == total_output_rows


# --- extract_structured_data activity tests ---

class TestExtractStructuredData:
    @pytest.mark.asyncio
    async def test_extracts_table_from_pdf(self, tmp_dir):
        path = os.path.join(tmp_dir, "table.pdf")
        _create_pdf_with_table(path, [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        params = ExtractionParams(job_id="test-sd-1", file_path=path)
        result = await extract_structured_data(params)

        assert isinstance(result, StructuredDataResult)
        assert len(result.tables) >= 1
        # Verify the table has rows with the expected data
        all_values = []
        for table in result.tables:
            for row in table.rows:
                all_values.extend([v for v in row.values if v])
        assert "Alice" in all_values or "Name" in all_values

    @pytest.mark.asyncio
    async def test_pdf_with_no_tables(self, tmp_dir):
        """A PDF with just text should return an empty table list."""
        import fitz

        path = os.path.join(tmp_dir, "notext.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Just some text, no tables here.")
        doc.save(path)
        doc.close()

        params = ExtractionParams(job_id="test-sd-2", file_path=path)
        result = await extract_structured_data(params)

        assert isinstance(result, StructuredDataResult)
        assert len(result.tables) == 0
