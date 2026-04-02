"""Data models for the PDF extraction system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import uuid


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExtractionParams:
    job_id: str
    file_path: str


@dataclass
class PageText:
    page_number: int
    text: str
    error: Optional[str] = None


@dataclass
class TextResult:
    pages: list[PageText]


@dataclass
class MetadataResult:
    title: Optional[str]
    author: Optional[str]
    subject: Optional[str]
    creation_date: Optional[str]
    modification_date: Optional[str]
    page_count: int
    file_size: int


@dataclass
class TableRow:
    values: list[Optional[str]]


@dataclass
class Table:
    rows: list[TableRow]
    page_number: int


@dataclass
class StructuredDataResult:
    tables: list[Table]


@dataclass
class ExtractionResult:
    text: TextResult
    metadata: MetadataResult
    structured_data: StructuredDataResult


@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    file_path: str = ""
    result: Optional[ExtractionResult] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StoreParams:
    job_id: str
    result: ExtractionResult


# --- Serialization utilities ---

def to_dict(obj: Any) -> Any:
    """Convert a dataclass instance (or primitive) to a plain dict/list/value."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [to_dict(item) for item in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {key: to_dict(getattr(obj, key)) for key in obj.__dataclass_fields__}
    return obj


def from_dict(cls: type, data: Any) -> Any:
    """Reconstruct a dataclass instance from a plain dict."""
    if data is None:
        return None

    if cls is JobStatus:
        return JobStatus(data)

    if cls is datetime:
        if isinstance(data, datetime):
            return data
        return datetime.fromisoformat(data)

    # Handle Optional types
    origin = getattr(cls, "__origin__", None)
    if origin is type(None):
        return None

    # typing.Optional[X] is Union[X, None]
    if origin is not None:
        import typing
        args = getattr(cls, "__args__", ())
        if type(None) in args:
            # Optional type — unwrap to the non-None arg
            inner = [a for a in args if a is not type(None)][0]
            return from_dict(inner, data)
        if origin is list:
            inner = args[0] if args else str
            return [from_dict(inner, item) for item in data]

    if not hasattr(cls, "__dataclass_fields__"):
        return data

    import typing
    field_types = typing.get_type_hints(cls)
    kwargs = {}
    for key, ftype in field_types.items():
        if key not in data:
            continue
        kwargs[key] = from_dict(ftype, data[key])
    return cls(**kwargs)
