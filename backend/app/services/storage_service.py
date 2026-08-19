"""Local file storage. TRD §11-12: random filenames, uploads kept outside
the executable directory, original files never modified.
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.utils.file_validation import (
    validate_extension,
    validate_mime_type,
    validate_size,
)
from app.utils.ids import new_id

CHUNK_SIZE = 1024 * 1024


@dataclass
class StoredUpload:
    stored_filename: str
    absolute_path: Path
    file_size: int
    file_hash: str
    extension: str


def save_upload(file: UploadFile) -> StoredUpload:
    ext = validate_extension(file.filename or "")
    validate_mime_type(file.content_type)

    stored_filename = f"{new_id()}{ext}"
    destination = settings.uploads_dir / stored_filename

    sha256 = hashlib.sha256()
    size = 0
    with destination.open("wb") as out:
        while chunk := file.file.read(CHUNK_SIZE):
            size += len(chunk)
            if size > settings.max_upload_size_bytes:
                out.close()
                destination.unlink(missing_ok=True)
                max_mb = settings.max_upload_size_bytes / (1024 * 1024)
                from app.utils.file_validation import UploadValidationError

                raise UploadValidationError(f"File exceeds maximum size of {max_mb:.0f} MB.")
            sha256.update(chunk)
            out.write(chunk)

    validate_size(size)

    return StoredUpload(
        stored_filename=stored_filename,
        absolute_path=destination,
        file_size=size,
        file_hash=sha256.hexdigest(),
        extension=ext,
    )


def compute_file_hash(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def copy_to_generated(source: Path, bill_id: str, filename: str) -> Path:
    target_dir = settings.generated_dir / bill_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    shutil.copyfile(source, target)
    return target


def delete_document_storage(stored_filename: str, document_id: str, bill_id: str | None = None) -> None:
    upload_path = settings.uploads_dir / stored_filename
    try:
        upload_path.unlink(missing_ok=True)
    except Exception:
        pass

    doc_images = settings.images_dir / document_id
    if doc_images.exists():
        shutil.rmtree(doc_images, ignore_errors=True)

    if bill_id:
        gen_dir = settings.generated_dir / bill_id
        if gen_dir.exists():
            shutil.rmtree(gen_dir, ignore_errors=True)
