"""Upload validation per TRD §11 (validate extension, MIME type, size)."""

from pathlib import Path

from app.core.config import settings


class UploadValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise UploadValidationError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(settings.allowed_extensions)}"
        )
    return ext


def validate_mime_type(content_type: str | None) -> None:
    if content_type not in settings.allowed_mime_types:
        raise UploadValidationError(f"Unsupported content type '{content_type}'.")


def validate_size(size_bytes: int) -> None:
    if size_bytes <= 0:
        raise UploadValidationError("Uploaded file is empty.")
    if size_bytes > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes / (1024 * 1024)
        raise UploadValidationError(f"File exceeds maximum size of {max_mb:.0f} MB.")


def sanitize_output_filename(name: str) -> str:
    """Sanitize a filename intended for generated PDF output."""
    keep = "-_. "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    cleaned = cleaned.replace(" ", "_")
    return cleaned or "file"
