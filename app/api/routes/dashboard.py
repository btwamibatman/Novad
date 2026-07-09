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

    language_distributions = db.scalars(
        select(Document.language_distribution)
        .where(
            Document.session_id == current_session.id,
            Document.status == "processed",
        )
    ).all()

    detected_languages: dict[str, float] = {}
    for distribution in language_distributions:
        if not isinstance(distribution, dict):
            continue
        for language, share in distribution.items():
            detected_languages[language] = round(detected_languages.get(language, 0.0) + float(share), 4)

    return DashboardSummary(
        total_documents=row.total_documents or 0,
        processed_documents=row.processed_documents or 0,
        failed_documents=row.failed_documents or 0,
        storage_bytes=row.storage_bytes or 0,
        detected_languages=detected_languages,
    )
