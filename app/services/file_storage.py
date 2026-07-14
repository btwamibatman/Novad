from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

CONTENT_TYPES_BY_EXTENSION = {
    ".pdf": "application/pdf",
}


def clean_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    clean_name = filename.replace("\\", "/").split("/")[-1].strip()
    if not clean_name or clean_name in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return clean_name[:255]


def resolve_content_type(filename: str, content_type: str | None) -> str:
    extension = Path(filename).suffix.lower()
    expected_type = CONTENT_TYPES_BY_EXTENSION.get(extension)
    if expected_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported",
        )
    normalized_type = "" if content_type is None else content_type.split(";")[0].strip()
    if normalized_type in {"", "application/octet-stream", expected_type}:
        return expected_type
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="File extension and content type do not match",
    )


async def save_upload(file: UploadFile) -> tuple[str, str, str, str, int]:
    filename = clean_filename(file.filename)
    content_type = resolve_content_type(filename, file.content_type)
    payload = await file.read()

    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(payload) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large")
    if b"%PDF-" not in payload[:1024]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file content is not a PDF",
        )

    upload_dir = Path(settings.storage_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4()}{Path(filename).suffix.lower()}"
    stored_file_path = upload_dir / stored_filename
    stored_file_path.write_bytes(payload)

    return filename, stored_filename, str(stored_file_path.resolve()), content_type, len(payload)


def resolve_stored_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if path.is_absolute() or path.exists():
        return path
    return Path(settings.storage_dir) / path


def remove_stored_file(stored_path: str) -> None:
    path = resolve_stored_path(stored_path)
    if path.exists() and path.is_file():
        path.unlink()
