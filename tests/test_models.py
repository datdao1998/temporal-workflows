"""Unit tests for data models and serialization utilities."""

from datetime import datetime

from src.models import (
    ExtractionParams,
    ExtractionResult,
    Job,
    JobStatus,
    MetadataResult,
    PageText,
    StoreParams,
    StructuredDataResult,
    Table,
    TableRow,
    TextResult,
    from_dict,
    to_dict,
)


def _make_extraction_result():
    """Helper to build a full ExtractionResult for testing."""
    text = TextResult(pages=[
        PageText(page_number=1, text="Hello world"),
        PageText(page_number=2, text="", error="corrupt page"),
    ])
    metadata = MetadataResult(
        title="Test PDF",
        author="Author",
        subject=None,
        creation_date="2024-01-01T00:00:00",
        modification_date=None,
        page_count=2,
        file_size=1024,
    )
    structured = StructuredDataResult(tables=[
        Table(rows=[TableRow(values=["a", "b"]), TableRow(values=["c", None])], page_number=1),
    ])
    return ExtractionResult(text=text, metadata=metadata, structured_data=structured)


class TestJobStatus:
    def test_enum_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_str_comparison(self):
        assert JobStatus.PENDING == "pending"


class TestDataclassCreation:
    def test_extraction_params(self):
        p = ExtractionParams(job_id="j1", file_path="/tmp/f.pdf")
        assert p.job_id == "j1"
        assert p.file_path == "/tmp/f.pdf"

    def test_page_text_defaults(self):
        pt = PageText(page_number=1, text="hi")
        assert pt.error is None

    def test_job_defaults(self):
        j = Job()
        assert j.status == JobStatus.PENDING
        assert j.file_path == ""
        assert j.result is None
        assert j.error is None
        assert isinstance(j.id, str) and len(j.id) > 0
        assert isinstance(j.created_at, datetime)

    def test_job_unique_ids(self):
        j1 = Job()
        j2 = Job()
        assert j1.id != j2.id


class TestToDict:
    def test_simple_dataclass(self):
        p = ExtractionParams(job_id="j1", file_path="/tmp/f.pdf")
        d = to_dict(p)
        assert d == {"job_id": "j1", "file_path": "/tmp/f.pdf"}

    def test_nested_dataclass(self):
        result = _make_extraction_result()
        d = to_dict(result)
        assert d["text"]["pages"][0]["text"] == "Hello world"
        assert d["text"]["pages"][1]["error"] == "corrupt page"
        assert d["metadata"]["title"] == "Test PDF"
        assert d["metadata"]["subject"] is None
        assert d["structured_data"]["tables"][0]["rows"][1]["values"] == ["c", None]

    def test_enum_serialization(self):
        j = Job(status=JobStatus.COMPLETED)
        d = to_dict(j)
        assert d["status"] == "completed"

    def test_datetime_serialization(self):
        dt = datetime(2024, 1, 15, 12, 30, 0)
        j = Job(created_at=dt, updated_at=dt)
        d = to_dict(j)
        assert d["created_at"] == "2024-01-15T12:30:00"

    def test_none_handling(self):
        assert to_dict(None) is None

    def test_empty_lists(self):
        tr = TextResult(pages=[])
        d = to_dict(tr)
        assert d == {"pages": []}


class TestFromDict:
    def test_simple_dataclass(self):
        d = {"job_id": "j1", "file_path": "/tmp/f.pdf"}
        p = from_dict(ExtractionParams, d)
        assert p.job_id == "j1"
        assert p.file_path == "/tmp/f.pdf"

    def test_nested_round_trip(self):
        original = _make_extraction_result()
        d = to_dict(original)
        restored = from_dict(ExtractionResult, d)
        assert restored.text.pages[0].text == "Hello world"
        assert restored.text.pages[1].error == "corrupt page"
        assert restored.metadata.title == "Test PDF"
        assert restored.metadata.subject is None
        assert restored.structured_data.tables[0].rows[1].values == ["c", None]

    def test_job_round_trip(self):
        original = Job(
            id="abc-123",
            status=JobStatus.FAILED,
            file_path="/tmp/test.pdf",
            error="something broke",
        )
        d = to_dict(original)
        restored = from_dict(Job, d)
        assert restored.id == "abc-123"
        assert restored.status == JobStatus.FAILED
        assert restored.error == "something broke"
        assert restored.result is None

    def test_job_with_result_round_trip(self):
        result = _make_extraction_result()
        original = Job(
            id="xyz",
            status=JobStatus.COMPLETED,
            file_path="/tmp/test.pdf",
            result=result,
        )
        d = to_dict(original)
        restored = from_dict(Job, d)
        assert restored.result is not None
        assert restored.result.text.pages[0].text == "Hello world"
        assert restored.result.metadata.page_count == 2

    def test_store_params_round_trip(self):
        result = _make_extraction_result()
        original = StoreParams(job_id="j1", result=result)
        d = to_dict(original)
        restored = from_dict(StoreParams, d)
        assert restored.job_id == "j1"
        assert restored.result.metadata.file_size == 1024

    def test_empty_pages_round_trip(self):
        original = TextResult(pages=[])
        d = to_dict(original)
        restored = from_dict(TextResult, d)
        assert restored.pages == []

    def test_empty_tables_round_trip(self):
        original = StructuredDataResult(tables=[])
        d = to_dict(original)
        restored = from_dict(StructuredDataResult, d)
        assert restored.tables == []
