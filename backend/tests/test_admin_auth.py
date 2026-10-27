import time
import pytest
from httpx import AsyncClient, ASGITransport
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from backend.app.main import app
from backend.app.config import settings
import backend.app.services.auth as auth_service


# Generate a persistent test RSA key pair for testing signature verification
_test_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)
_test_public_key = _test_private_key.public_key()
_test_public_pem = _test_public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")


class MockSigningKey:
    def __init__(self, key):
        self.key = key


class MockJWKSClient:
    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, token):
        return MockSigningKey(self._key)


TEST_TENANT_ID = "test-tenant-uuid-1234"
TEST_CLIENT_ID = "test-client-uuid-5678"
TEST_ADMIN_EMAIL = "test.admin@example.com"
TEST_ADMIN_OBJECT_ID = "test-object-uuid-9012"


def _make_test_jwt(
    email: str = TEST_ADMIN_EMAIL,
    tenant_id: str = TEST_TENANT_ID,
    client_id: str = TEST_CLIENT_ID,
    expired: bool = False,
    issuer: str = None,
    audience: str = None,
    object_id: str = TEST_ADMIN_OBJECT_ID,
    scope: str = "admin.access",
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer or f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "aud": audience or f"api://{client_id}",
        "tid": tenant_id,
        "preferred_username": email,
        "name": "Test Administrator",
        "iat": now - 600,
        "exp": (now - 300) if expired else (now + 3600),
        "sub": "test-subject-12345",
        "oid": object_id,
        "scp": scope,
    }
    return jwt.encode(payload, _test_private_key, algorithm="RS256", headers={"kid": "test-kid"})


@pytest.mark.asyncio
async def test_admin_rejects_missing_token():
    settings.AUTH_MODE = "entra"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/admin/applications")
        assert res.status_code == 401
        assert "Missing Bearer authentication token" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_rejects_malformed_token():
    settings.AUTH_MODE = "entra"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer not-a-valid-jwt-token"}
        res = await client.get("/admin/applications", headers=headers)
        assert res.status_code == 401
        assert "Invalid or expired Entra access token" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_rejects_unauthorized_object_id(monkeypatch):
    settings.AUTH_MODE = "entra"
    settings.ENTRA_TENANT_ID = TEST_TENANT_ID
    settings.ENTRA_CLIENT_ID = TEST_CLIENT_ID
    settings.ADMIN_ALLOWED_OBJECT_IDS = [TEST_ADMIN_OBJECT_ID]
    monkeypatch.setattr(auth_service, "get_jwks_client", lambda: MockJWKSClient(_test_public_key))

    token = _make_test_jwt(object_id="unauthorized-object-id")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.get("/admin/applications", headers=headers)
        assert res.status_code == 403
        assert "not authorized" in res.json()["detail"]


@pytest.mark.asyncio
async def test_admin_rejects_expired_token(monkeypatch):
    settings.AUTH_MODE = "entra"
    settings.ENTRA_TENANT_ID = TEST_TENANT_ID
    settings.ENTRA_CLIENT_ID = TEST_CLIENT_ID
    settings.ADMIN_ALLOWED_OBJECT_IDS = [TEST_ADMIN_OBJECT_ID]
    monkeypatch.setattr(auth_service, "get_jwks_client", lambda: MockJWKSClient(_test_public_key))

    token = _make_test_jwt(email=TEST_ADMIN_EMAIL, expired=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.get("/admin/applications", headers=headers)
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_accepts_valid_entra_token(monkeypatch):
    settings.AUTH_MODE = "entra"
    settings.ENTRA_TENANT_ID = TEST_TENANT_ID
    settings.ENTRA_CLIENT_ID = TEST_CLIENT_ID
    settings.ADMIN_ALLOWED_OBJECT_IDS = [TEST_ADMIN_OBJECT_ID]
    monkeypatch.setattr(auth_service, "get_jwks_client", lambda: MockJWKSClient(_test_public_key))

    token = _make_test_jwt(email=TEST_ADMIN_EMAIL)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.get("/admin/applications", headers=headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_admin_rejects_graph_audience(monkeypatch):
    settings.AUTH_MODE = "entra"
    settings.ENTRA_TENANT_ID = TEST_TENANT_ID
    settings.ENTRA_CLIENT_ID = TEST_CLIENT_ID
    monkeypatch.setattr(auth_service, "get_jwks_client", lambda: MockJWKSClient(_test_public_key))

    token = _make_test_jwt(audience="https://graph.microsoft.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/admin/applications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_admin_rejects_token_without_required_scope(monkeypatch):
    settings.AUTH_MODE = "entra"
    settings.ENTRA_TENANT_ID = TEST_TENANT_ID
    settings.ENTRA_CLIENT_ID = TEST_CLIENT_ID
    monkeypatch.setattr(auth_service, "get_jwks_client", lambda: MockJWKSClient(_test_public_key))

    token = _make_test_jwt(scope="User.Read")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/admin/applications",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert "does not grant" in res.json()["detail"]


def test_production_rejects_disabled_authentication():
    settings.ENV = "production"
    settings.AUTH_MODE = "disabled"
    with pytest.raises(RuntimeError, match="not permitted in production"):
        settings.validate_runtime_configuration()
