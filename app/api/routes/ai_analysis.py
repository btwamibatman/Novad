from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_session
from app.core.config import settings
from app.core.database import get_db
from app.models.ai_analysis_job import AIAnalysisJob
from app.models.session import UserSession
from app.schemas.ai_analysis import AIAnalysisJobCreate, AIAnalysisJobRead, AIProviderInfo
from app.services.ai.jobs import (
    AIAnalysisConsentRequired,
    AIAnalysisJobNotCancellable,
    AIAnalysisJobsActive,
    cancel_ai_job,
    delete_remote_copy,
    enqueue_ai_analysis,
    reconcile_expired_remote_files,
)
from app.services.ai.provider import AIProviderError, AIProviderNotConfigured
from app.services.documents.artifacts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactNotReadyError,
)
from app.services.rate_limit import enforce_rate_limit

router = APIRouter()


@router.get("/provider-info", response_model=AIProviderInfo)
def read_ai_provider_info(
    current_session: UserSession = Depends(get_current_session),
) -> AIProviderInfo:
    del current_session
    model = (
        settings.gemini_model
        if settings.ai_provider.strip().lower() == "gemini"
        else "configured"
    )
    return AIProviderInfo(
        provider=settings.ai_provider,
        model=model,
        service_tier=settings.gemini_service_tier,
    )


@router.get("/jobs", response_model=list[AIAnalysisJobRead])
def list_ai_jobs(
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> list[AIAnalysisJob]:
    reconcile_expired_remote_files(db, user_id=current_session.user_id)
    return list(
        db.scalars(
            select(AIAnalysisJob)
            .where(AIAnalysisJob.user_id == current_session.user_id)
            .order_by(AIAnalysisJob.created_at.desc(), AIAnalysisJob.id.desc())
            .limit(50)
        )
    )


@router.get("/jobs/{job_id}", response_model=AIAnalysisJobRead)
def read_ai_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIAnalysisJob:
    return _owned_job(db, job_id, current_session.user_id)


@router.post(
    "/jobs",
    response_model=AIAnalysisJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_ai_job(
    payload: AIAnalysisJobCreate,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIAnalysisJob:
    await enforce_rate_limit(
        f"user:{current_session.user_id}",
        "protected-ai-analysis",
        limit=10,
    )
    try:
        return enqueue_ai_analysis(
            db,
            user_id=current_session.user_id,
            payload=payload,
        )
    except AIAnalysisConsentRequired as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except ArtifactNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except (ArtifactNotReadyError, ArtifactIntegrityError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.delete("/jobs/{job_id}/remote-file", response_model=AIAnalysisJobRead)
def delete_ai_job_remote_file(
    job_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIAnalysisJob:
    job = _owned_job(db, job_id, current_session.user_id)
    try:
        return delete_remote_copy(db, job)
    except AIAnalysisJobsActive as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except AIProviderNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except AIProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to delete the external AI copy",
        ) from error


@router.post("/jobs/{job_id}/cancel", response_model=AIAnalysisJobRead)
def cancel_ai_analysis_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIAnalysisJob:
    job = _owned_job(db, job_id, current_session.user_id)
    try:
        return cancel_ai_job(db, job)
    except AIAnalysisJobNotCancellable as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except AIProviderNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except AIProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI job was cancelled, but the external copy could not be deleted",
        ) from error


def _owned_job(db: Session, job_id: int, user_id: int) -> AIAnalysisJob:
    reconcile_expired_remote_files(db, user_id=user_id)
    job = db.scalar(
        select(AIAnalysisJob).where(
            AIAnalysisJob.id == job_id,
            AIAnalysisJob.user_id == user_id,
        )
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI analysis job was not found",
        )
    return job
