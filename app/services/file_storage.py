from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import settings

CONTENT_TYPES_BY_EXTENSION = {
    ".pdf": "application/pdf",
}
UPLOAD_CHUNK_SIZE = 1024 * 1024


def validate_pdf(stored_file_path: Path) -> None:
    try:
        reader = PdfReader(str(stored_file_path))
        if reader.is_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password-protected PDF files are not supported",
            )
        page_count = len(reader.pages)
    except HTTPException:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file is not a valid PDF",
        ) from error

    if page_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF must contain at least one page",
        )
    if page_count > settings.max_pdf_pages:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds the {settings.max_pdf_pages}-page limit",
        )


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

    upload_dir = Path(settings.storage_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4()}{Path(filename).suffix.lower()}"
    stored_file_path = upload_dir / stored_filename
    size_bytes = 0
    first_bytes = bytearray()
    try:
        with stored_file_path.open("wb") as stored_file:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File is too large",
                    )
                if len(first_bytes) < 1024:
                    first_bytes.extend(chunk[: 1024 - len(first_bytes)])
                stored_file.write(chunk)

        if size_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )
        if not first_bytes.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Uploaded file content is not a PDF",
            )
        validate_pdf(stored_file_path)
    except Exception:
        stored_file_path.unlink(missing_ok=True)
        raise

    return filename, stored_filename, str(stored_file_path.resolve()), content_type, size_bytes


def resolve_stored_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if path.is_absolute() or path.exists():
        return path
    return Path(settings.storage_dir) / path


def remove_stored_file(stored_path: str) -> None:
    path = resolve_stored_path(stored_path)
    if path.exists() and path.is_file():
        path.unlink()
