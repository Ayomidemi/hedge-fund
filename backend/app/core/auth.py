import ssl
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import certifi
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None
    full_name: str | None = None
    org_name: str | None = None
    role: str | None = None
    starting_capital: Decimal | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client

    if not settings.supabase_url:
        return None

    if _jwks_client is None:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            ssl_context=ssl_context,
        )

    return _jwks_client


def _decode_supabase_token(token: str) -> dict:
    if settings.hf_supabase_jwt_secret:
        try:
            return jwt.decode(
                token,
                settings.hf_supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Sign in again.",
            ) from exc
        except jwt.InvalidTokenError:
            pass

    jwks_client = _get_jwks_client()
    if jwks_client is not None:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[signing_key.algorithm_name],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Sign in again.",
            ) from exc
        except jwt.InvalidTokenError:
            pass
        except PyJWKClientConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify authentication token. Try again shortly.",
            ) from exc

    if not settings.hf_supabase_jwt_secret and jwks_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase JWT verification is not configured.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token.",
    )


def _user_from_payload(payload: dict) -> AuthenticatedUser:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing a user id.",
        )

    app_metadata = payload.get("app_metadata") or {}
    user_metadata = payload.get("user_metadata") or {}
    email = payload.get("email") or user_metadata.get("email")
    role = app_metadata.get("role") or payload.get("role")
    full_name = user_metadata.get("full_name")
    org_name = user_metadata.get("org_name")
    starting_capital = _starting_capital_from_metadata(user_metadata)

    return AuthenticatedUser(
        id=str(user_id),
        email=str(email) if email else None,
        full_name=str(full_name) if full_name else None,
        org_name=str(org_name) if org_name else None,
        role=str(role) if role else None,
        starting_capital=starting_capital,
    )


def _starting_capital_from_metadata(metadata: dict) -> Decimal | None:
    value = metadata.get("starting_capital")
    if value is None or value == "":
        return None

    try:
        capital = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

    minimum = Decimal("1000.00")
    if capital < minimum:
        return minimum
    return capital.quantize(Decimal("0.01"))


def authenticate_token(token: str) -> AuthenticatedUser:
    """Validate a raw JWT (used by the WebSocket handshake, where FastAPI's
    HTTP bearer dependency is unavailable). Raises HTTPException on failure."""
    if not settings.auth_enabled:
        return AuthenticatedUser(id="anonymous", email=None, role="anonymous")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    payload = _decode_supabase_token(token)
    return _user_from_payload(payload)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser | None:
    if not settings.auth_enabled:
        return None

    if credentials is None or not credentials.credentials:
        return None

    payload = _decode_supabase_token(credentials.credentials)
    return _user_from_payload(payload)


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    if not settings.auth_enabled:
        return AuthenticatedUser(id="anonymous", email=None, role="anonymous")

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_supabase_token(credentials.credentials)
    return _user_from_payload(payload)
