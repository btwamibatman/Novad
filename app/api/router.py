from fastapi import APIRouter

from app.api.routes import dashboard, documents

api_router = APIRouter(prefix="/api")
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
