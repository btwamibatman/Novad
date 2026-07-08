from fastapi import APIRouter

from app.api.routes import dashboard, documents, session

api_router = APIRouter(prefix="/api")
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
