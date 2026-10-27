from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient, PyJWTError
from backend.app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# Lazy JWKS client instance
_jwks_client: Optional[PyJWKClient] = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/discovery/v2.0/keys"
        _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


async def verify_admin_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Dict[str, Any]:
    """
    Validate an Entra access token issued specifically for the DearBot API.

    Local development can use AUTH_MODE=disabled. Production configuration is
    validated at startup and cannot use the bypass.
    """
    if settings.resolved_auth_mode == "disabled":
        if settings.ENV.lower() not in ("development", "test", "testing"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Administrative authentication is not configured",
            )
        return {
            "name": "Local developer",
            "sub": "dev-bypass",
            "oid": "dev-bypass",
            "tid": "dev-tenant",
            "auth_mode": "disabled",
        }

    if settings.resolved_auth_mode != "entra":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsupported administrative authentication mode",
        )

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    expected_issuer = f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/v2.0"

    try:
        jwks = get_jwks_client()
        signing_key = jwks.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.entra_audience,
            issuer=expected_issuer,
            leeway=30,
            options={"verify_exp": True, "verify_iss": True, "verify_aud": True},
        )
    except PyJWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Entra access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Entra token verification failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate Tenant ID
    tid = payload.get("tid")
    if tid != settings.ENTRA_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token was issued by an unauthorized tenant",
        )

    scopes = set(str(payload.get("scp") or "").split())
    roles = set(payload.get("roles") or [])
    required_permission = settings.ENTRA_REQUIRED_SCOPE
    if required_permission not in scopes and required_permission not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not grant DearBot administrative access",
        )

    object_id = str(payload.get("oid") or "")
    allowed_object_ids = {value.strip() for value in settings.ADMIN_ALLOWED_OBJECT_IDS if value.strip()}
    if not object_id or (allowed_object_ids and object_id not in allowed_object_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Entra principal is not authorized for this DearBot instance",
        )

    return payload
