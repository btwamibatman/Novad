from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.core.database import get_db
from app.models.document import Document
from app.models.session import UserSession
from app.schemas.dashboard import DashboardSummary

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
def read_dashboard_summary(
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> DashboardSummary:
    row = db.execute(
        select(
            select(func.count(Document.id))
            .where(Document.session_id == current_session.id)
            .scalar_subquery()
            .label("total_documents"),
            select(func.count(Document.id))
            .where(Document.session_id == current_session.id, Document.status == "processed")
            .scalar_subquery()
            .label("processed_documents"),
            select(func.count(Document.id))
            .where(Document.session_id == current_session.id, Document.status == "failed")
            .scalar_subquery()
            .label("failed_documents"),
            select(func.coalesce(func.sum(Document.size_bytes), 0))
            .where(Document.session_id == current_session.id)
            .scalar_subquery()
            .label("storage_bytes"),
        )
    ).one()

    language_rows = db.execute(
        select(Document.detected_language, func.count(Document.id))
        .where(
            Document.session_id == current_session.id,
            Document.detected_language.is_not(None),
        )
        .group_by(Document.detected_language)
    ).all()

    return DashboardSummary(
        total_documents=row.total_documents or 0,
        processed_documents=row.processed_documents or 0,
        failed_documents=row.failed_documents or 0,
        storage_bytes=row.storage_bytes or 0,
        detected_languages={
            language: count for language, count in language_rows if language is not None
        },
    )
