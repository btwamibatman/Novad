from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import create_session, init_db
from app.models.document import Document
from app.models.session import UserSession
from app.services.text_analysis import analyze_text

SAMPLE_TEXT = (
    "Document Processing API stores uploaded document metadata, extracts text, "
    "detects language and prepares useful metrics for backend reporting."
)


def seed_demo_document(db: Session) -> bool:
    existing_documents = db.scalar(select(func.count(Document.id)))
    if existing_documents:
        print("Seed skipped: documents already exist.")
        return False

    upload_dir = Path(settings.storage_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4()}.txt"
    stored_file_path = upload_dir / stored_filename
    stored_file_path.write_text(SAMPLE_TEXT, encoding="utf-8")

    detected_language, word_count, char_count = analyze_text(SAMPLE_TEXT)
    db_session = UserSession()
    db.add(db_session)
    db.flush()
    db.add(
        Document(
            session_id=db_session.id,
            filename="sample-document.txt",
            stored_filename=stored_filename,
            stored_path=stored_filename,
            content_type="text/plain",
            size_bytes=stored_file_path.stat().st_size,
            status="processed",
            extracted_text=SAMPLE_TEXT,
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
