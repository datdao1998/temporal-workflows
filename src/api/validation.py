"""PDF validation utilities for the API layer."""

# Default maximum file size: 50 MB
DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024

# PDF magic bytes
PDF_MAGIC_BYTES = b"%PDF"


class PDFValidationError(Exception):
    """Raised when PDF validation fails (HTTP 400)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds the size limit (HTTP 413)."""

    def __init__(self, message: str, max_size: int):
        self.message = message
        self.max_size = max_size
        super().__init__(message)


def validate_pdf_magic_bytes(data: bytes) -> None:
    """Validate that the file content starts with PDF magic bytes (%PDF).

    Args:
        data: The raw file bytes (at least the first 4 bytes are needed).

    Raises:
        PDFValidationError: If the data does not start with %PDF.
    """
    if not data or not data[:4].startswith(PDF_MAGIC_BYTES):
        raise PDFValidationError("File is not a valid PDF: missing %PDF header")


def validate_file_size(size: int, max_size: int = DEFAULT_MAX_FILE_SIZE) -> None:
    """Validate that the file size is within the allowed limit.

    Args:
        size: The file size in bytes.
        max_size: Maximum allowed size in bytes (default 50 MB).

    Raises:
        FileTooLargeError: If the file exceeds the maximum size.
    """
    if size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise FileTooLargeError(
            f"File size exceeds the maximum allowed limit of {max_mb:.0f}MB",
            max_size=max_size,
        )


def validate_pdf(data: bytes, max_size: int = DEFAULT_MAX_FILE_SIZE) -> None:
    """Run all PDF validations: magic bytes and file size.

    Args:
        data: The raw file bytes.
        max_size: Maximum allowed size in bytes (default 50 MB).

    Raises:
        PDFValidationError: If the file is not a valid PDF.
        FileTooLargeError: If the file exceeds the size limit.
    """
    validate_file_size(len(data), max_size)
    validate_pdf_magic_bytes(data)
