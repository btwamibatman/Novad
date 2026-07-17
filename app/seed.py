from pathlib import Path
from uuid import uuid4

import pymupdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import create_session, init_db
from app.models.document import Document
from app.models.user import User
from app.services.text_analysis import (
    ExtractedPage,
    analyze_text,
    assess_extraction_quality,
)

SAMPLE_TEXT = (
    "Document Processing API stores uploaded document metadata, extracts text, "
    "detects language and prepares useful metrics for backend reporting."
)


def seed_demo_document(db: Session) -> bool:
    existing_documents = db.scalar(select(func.count(Document.id)))
    if existing_documents:
        print("Seed skipped: documents already exist.")
        return False

    db_user = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
    if db_user is None:
        print("Seed skipped: create an active user first with python -m app.create_user.")
        return False

    upload_dir = Path(settings.storage_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4()}.pdf"
    stored_file_path = upload_dir / stored_filename
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox(
            pymupdf.Rect(72, 72, page.rect.width - 72, page.rect.height - 72),
            SAMPLE_TEXT,
            fontsize=12,
        )
        pdf.save(stored_file_path)

    detected_language, word_count, char_count = analyze_text(SAMPLE_TEXT)
    extraction_quality = assess_extraction_quality(
        [ExtractedPage(1, SAMPLE_TEXT, "pypdf")]
    )
    db.add(
        Document(
            user_id=db_user.id,
            session_id=None,
            filename="sample-document.pdf",
            stored_filename=stored_filename,
            stored_path=stored_filename,
            content_type="application/pdf",
            size_bytes=stored_file_path.stat().st_size,
            status="processed",
            extracted_text=SAMPLE_TEXT,
            extraction_quality=extraction_quality.quality,
            extraction_quality_meta=extraction_quality.meta,
            detected_language=detected_language,
            word_count=word_count,
            char_count=char_count,
        )
    )
    db.commit()
    print("Seeded one processed demo document.")
    return True


def main() -> None:
    init_db()
    db = create_session()
    try:
        seed_demo_document(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
