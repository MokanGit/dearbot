from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.app.config import settings
from backend.app.database import init_db, AsyncSessionLocal
from backend.app.services.google_drive import GoogleDriveService
from backend.app.api.public import router as public_router
from backend.app.api.admin import router as admin_router
from backend.app.api.mcp import router as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime_configuration()
    # Initialize DB tables
    await init_db()

    # Pre-seed canonical documents if database is empty
    async with AsyncSessionLocal() as session:
        drive_service = GoogleDriveService()
        await drive_service.sync_documents(session)

    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Evidence-grounded CV and application generation",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.ENV.lower() == "production" else "/docs",
    redoc_url=None if settings.ENV.lower() == "production" else "/redoc",
    openapi_url=None if settings.ENV.lower() == "production" else "/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

# CORS is an explicit browser allowlist, not an authentication boundary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Access-Method", "X-WebMCP-Tool"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.ENV.lower() == "production":
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
    return response

# Register API Routers
app.include_router(public_router)
app.include_router(admin_router)
app.include_router(mcp_router)


import os
from fastapi import Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models import Document


@app.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    provider_name = settings.LLM_PROVIDER.lower()
    has_api_key = bool(
        (provider_name == "gemini" and settings.GEMINI_API_KEY) or
        (provider_name == "openai" and settings.OPENAI_API_KEY) or
        (provider_name == "mock" and settings.ENV.lower() != "production")
    )
    llm_status = "operational" if has_api_key else "misconfigured"

    # Query public canonical documents
    doc_stmt = select(func.count(Document.id)).where(Document.classification == "public")
    doc_res = await session.execute(doc_stmt)
    public_doc_count = doc_res.scalar() or 0

    drive_configured = bool(
        (settings.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(settings.GOOGLE_SERVICE_ACCOUNT_FILE)) or
        (settings.GOOGLE_CREDENTIALS_FILE and os.path.exists(settings.GOOGLE_CREDENTIALS_FILE))
    )

    is_degraded = (not has_api_key) or (public_doc_count == 0)
    overall_status = "degraded" if is_degraded else "healthy"

    return {
        "status": overall_status,
        "environment": settings.ENV,
        "app": settings.APP_NAME,
        "candidate": settings.CANDIDATE_NAME,
        "llm": {
            "provider": settings.LLM_PROVIDER,
            "status": llm_status,
            "model": settings.GEMINI_MODEL if provider_name == "gemini" else settings.OPENAI_MODEL,
            "configured": has_api_key
        },
        "corpus": {
            "public_documents_count": public_doc_count,
            "drive_credentials_present": drive_configured
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
