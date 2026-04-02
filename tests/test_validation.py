"""Unit tests for PDF validation utilities."""

import pytest

from src.api.validation import (
    DEFAULT_MAX_FILE_SIZE,
    FileTooLargeError,
    PDFValidationError,
    validate_file_size,
    validate_pdf,
    validate_pdf_magic_bytes,
)


# --- validate_pdf_magic_bytes ---


class TestValidatePdfMagicBytes:
    def test_valid_pdf_header(self):
        data = b"%PDF-1.4 some content"
        validate_pdf_magic_bytes(data)  # should not raise

    def test_minimal_valid_header(self):
        data = b"%PDF"
        validate_pdf_magic_bytes(data)  # should not raise

    def test_empty_bytes_raises(self):
        with pytest.raises(PDFValidationError, match="not a valid PDF"):
            validate_pdf_magic_bytes(b"")

    def test_random_bytes_raises(self):
        with pytest.raises(PDFValidationError, match="not a valid PDF"):
            validate_pdf_magic_bytes(b"\x00\x01\x02\x03")

    def test_almost_pdf_header_raises(self):
        with pytest.raises(PDFValidationError, match="not a valid PDF"):
            validate_pdf_magic_bytes(b"%PD")

    def test_png_header_raises(self):
        with pytest.raises(PDFValidationError, match="not a valid PDF"):
            validate_pdf_magic_bytes(b"\x89PNG\r\n\x1a\n")

    def test_text_file_raises(self):
        with pytest.raises(PDFValidationError, match="not a valid PDF"):
            validate_pdf_magic_bytes(b"Hello, world!")


# --- validate_file_size ---


class TestValidateFileSize:
    def test_within_default_limit(self):
        validate_file_size(1024)  # 1 KB — should not raise

    def test_exactly_at_limit(self):
        validate_file_size(DEFAULT_MAX_FILE_SIZE)  # should not raise

    def test_exceeds_default_limit(self):
        with pytest.raises(FileTooLargeError, match="50MB"):
            validate_file_size(DEFAULT_MAX_FILE_SIZE + 1)

    def test_custom_limit(self):
        custom_limit = 10 * 1024 * 1024  # 10 MB
        validate_file_size(custom_limit)  # exactly at limit — ok
        with pytest.raises(FileTooLargeError, match="10MB"):
            validate_file_size(custom_limit + 1, max_size=custom_limit)

    def test_zero_size_ok(self):
        validate_file_size(0)  # should not raise

    def test_error_includes_max_size(self):
        limit = 5 * 1024 * 1024
        with pytest.raises(FileTooLargeError) as exc_info:
            validate_file_size(limit + 1, max_size=limit)
        assert exc_info.value.max_size == limit


# --- validate_pdf (combined) ---


class TestValidatePdf:
    def test_valid_small_pdf(self):
        data = b"%PDF-1.7 fake pdf content"
        validate_pdf(data)  # should not raise

    def test_invalid_header_raises_validation_error(self):
        data = b"not a pdf"
        with pytest.raises(PDFValidationError):
            validate_pdf(data)

    def test_oversized_raises_file_too_large(self):
        # File too large is checked first
        data = b"%PDF" + b"\x00" * DEFAULT_MAX_FILE_SIZE
        with pytest.raises(FileTooLargeError):
            validate_pdf(data)

    def test_oversized_non_pdf_raises_file_too_large(self):
        # Size check runs before magic bytes check
        data = b"\x00" * (DEFAULT_MAX_FILE_SIZE + 1)
        with pytest.raises(FileTooLargeError):
            validate_pdf(data)

    def test_custom_max_size(self):
        small_limit = 100
        data = b"%PDF" + b"\x00" * 200
        with pytest.raises(FileTooLargeError):
            validate_pdf(data, max_size=small_limit)
