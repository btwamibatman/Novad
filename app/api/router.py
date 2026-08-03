from fastapi import APIRouter

from app.api.routes import auth, dashboard, documents, session, tools

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(session.router, prefix="/session", tags=["session"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
