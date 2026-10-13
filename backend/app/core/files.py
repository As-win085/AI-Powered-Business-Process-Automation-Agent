import hashlib
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError, ValidationError

_MAGIC_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("application/pdf", b"%PDF-"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
)

_OCTET_STREAM = "application/octet-stream"
_READ_CHUNK_SIZE = 1024 * 1024


def sniff_content_type(data: bytes) -> str | None:
    """Return the MIME type inferred from the file's magic bytes, if recognized."""
    for content_type, signature in _MAGIC_SIGNATURES:
        if data.startswith(signature):
            return content_type
    return None


def read_upload(upload: UploadFile) -> bytes:
    """Read an upload into memory, enforcing the configured size limit.

    Raises PayloadTooLargeError as soon as the limit is crossed so an oversized
    upload never has to be fully buffered on disk.
    """
    limit = settings.max_upload_size_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(
                f"File exceeds the maximum allowed size of {settings.max_upload_size_mb} MB"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def validate_upload(filename: str, content_type: str | None, data: bytes) -> str:
    """Validate extension, declared MIME type and magic bytes.

    Returns the recognized MIME type. Raises ValidationError on any mismatch so
    the API can never store a file whose content disagrees with its extension.
    """
    if not filename or not filename.strip():
        raise ValidationError("A file name is required")
    if not data:
        raise ValidationError("The uploaded file is empty")

    extension = Path(filename).suffix.lower()
    allowed = settings.allowed_upload_content_types
    if extension not in allowed:
        allowed_extensions = ", ".join(sorted(allowed)) or "(none configured)"
        raise ValidationError(
            f"Unsupported file extension '{extension}'. Allowed: {allowed_extensions}"
        )

    expected_types = allowed[extension]
    if content_type and content_type != _OCTET_STREAM and content_type not in expected_types:
        raise ValidationError(f"Content type '{content_type}' is not valid for '{extension}' files")

    sniffed = sniff_content_type(data)
    if sniffed is None:
        raise ValidationError("Unrecognized or unsupported file content")
    if sniffed not in expected_types:
        raise ValidationError(
            f"File content ({sniffed}) does not match its '{extension}' extension"
        )
    return sniffed


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
