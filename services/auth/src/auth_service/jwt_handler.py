"""
JWT token creation and validation.

SRP: Only handles token lifecycle — creation, decoding, revocation check.
All ABAC policy decisions are in abac.py (separated concern).
"""
import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

import structlog

from auth_service.config import settings
from auth_service.models import TokenClaims, UserRole

log = structlog.get_logger(__name__)


def _pseudonymise_email(email: str, tenant_id: str) -> str:
    """GDPR Art.25: HMAC-SHA256 pseudonym. Never store raw email in tokens."""
    key = f"{settings.jwt_secret_key}:{tenant_id}".encode()
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()[:32]


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: UserRole,
    email: str,
    kong_kid: str,
    expire_minutes: int | None = None,
) -> tuple[str, TokenClaims]:
    """
    Create a signed JWT for Kong consumption.

    The `kid` field matches the Kong consumer JWT secret key_id,
    enabling Kong to look up the right secret for verification.
    """
    expire_mins = min(
        expire_minutes or settings.jwt_access_token_expire_minutes,
        settings.jwt_max_expire_minutes,
    )
    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + (expire_mins * 60)

    claims = TokenClaims(
        sub=user_id,
        tenant_id=tenant_id,
        role=role,
        email_hash=_pseudonymise_email(email, tenant_id),
        exp=exp,
        nbf=now,
        iat=now,
        kid=kong_kid,
        jti=str(uuid.uuid4()),
    )

    token = jwt.encode(
        claims.model_dump(),
        key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    log.info(
        "jwt.created",
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        exp=exp,
        jti=claims.jti,
    )
    return token, claims


def decode_token(token: str) -> TokenClaims:
    """Decode and validate a JWT. Raises JWTError on failure."""
    try:
        payload = jwt.decode(
            token,
            key=settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenClaims(**payload)
    except ExpiredSignatureError:
        log.warning("jwt.expired")
        raise
    except JWTError as e:
        log.warning("jwt.invalid", error=str(e))
        raise
