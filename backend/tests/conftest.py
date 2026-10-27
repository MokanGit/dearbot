import pytest
from backend.app.database import init_db, AsyncSessionLocal

from backend.app.config import settings

@pytest.fixture(autouse=True)
async def setup_db():
    settings.AUTH_MODE = "disabled"
    settings.ENV = "test"
    settings.ADMIN_ALLOWED_OBJECT_IDS = []
    settings.ENTRA_AUDIENCE = ""
    settings.ENTRA_REQUIRED_SCOPE = "admin.access"
    from backend.app.services.security import rate_limiter
    rate_limiter._requests.clear()
    rate_limiter._general_requests.clear()
    await init_db()

@pytest.fixture
async def db_session():
    await init_db()
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()
