import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import create_session, init_db
from app.crud.session import cleanup_expired_sessions
from app.middleware.request_size import RequestSizeLimitMiddleware


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
WEB_DIST_DIR = WEB_DIR / "dist"
WEB_INDEX = WEB_DIST_DIR / "index.html"


async def cleanup_expired_sessions_loop() -> None:
    while True:
        await asyncio.sleep(settings.session_cleanup_interval_seconds)
        db = create_session()
        try:
            cleanup_expired_sessions(db)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    cleanup_task = asyncio.create_task(cleanup_expired_sessions_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description="Backend API for PDF OCR, text analysis, AI content review and visual layout review.",
    lifespan=lifespan,
    middleware=[
        Middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_host_list,
            www_redirect=False,
        ),
        Middleware(
            RequestSizeLimitMiddleware,
            max_bytes=settings.max_request_size_bytes,
        ),
    ],
)

app.include_router(api_router)
app.mount(
    "/web/dist",
    StaticFiles(directory=WEB_DIST_DIR, check_dir=False),
    name="web",
)


@app.get("/", include_in_schema=False)
@app.get("/documents", include_in_schema=False)
@app.get("/tools", include_in_schema=False)
def web_interface() -> FileResponse:
    if not WEB_INDEX.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Frontend build is unavailable; run npm run build in frontend/",
        )
    return FileResponse(WEB_INDEX)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "project": settings.project_name,
    }
