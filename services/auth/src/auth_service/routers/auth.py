"""
Auth router — login, token refresh, logout, ABAC evaluation.

Day 3: Full JWT issue + ABAC policy endpoint.
"""
import hashlib
import hmac

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from auth_service.abac import ABACPolicyEngine
from auth_service.config import settings
from auth_service.jwt_handler import create_access_token, decode_token
from auth_service.models import (
    ABACRequest,
    ABACResponse,
    LoginRequest,
    TokenClaims,
    TokenResponse,
    UserRole,
)

log = structlog.get_logger(__name__)
router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)
_abac = ABACPolicyEngine()

# ---- Dependency: extract + validate JWT from request ----------------------

async def get_current_claims(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    request: Request = None,
) -> TokenClaims:
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_token(creds.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---- Endpoints ------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate user and issue JWT.
    Day 3 implementation: password hash check against PostgreSQL users table.

    Note: In production this integrates with the SSO provider (SAML/OIDC).
    The local login is for API keys and service accounts only.
    """
    # TODO Day 24: Replace with SAML/OIDC SSO flow
    # For now: accept demo credentials in dev mode
    if settings.env != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local login disabled in non-dev environments. Use SSO.",
        )

    # Dev-only credential check (replaced by real DB lookup in Day 24)
    demo_users = {
        "admin@demo.datamind.ai": {"role": UserRole.ADMIN, "user_id": "demo-admin-001"},
        "analyst@demo.datamind.ai": {"role": UserRole.ANALYST, "user_id": "demo-analyst-001"},
        "ds@demo.datamind.ai": {"role": UserRole.DATA_SCIENTIST, "user_id": "demo-ds-001"},
    }

    user_info = demo_users.get(req.email)
    if not user_info or req.password != "datamind-dev":  # noqa: S105
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    tenant_id = "00000000-0000-0000-0000-000000000001"  # demo tenant
    kong_kid = "demo-tenant-key"

    token, claims = create_access_token(
        user_id=user_info["user_id"],
        tenant_id=tenant_id,
        role=user_info["role"],
        email=req.email,
        kong_kid=kong_kid,
    )

    log.info("auth.login.success", user_id=user_info["user_id"], tenant_id=tenant_id)

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        tenant_id=tenant_id,
        role=user_info["role"],
    )


@router.post("/logout")
async def logout(
    claims: TokenClaims = Depends(get_current_claims),
    request: Request = None,
):
    """
    Revoke a token by storing its JTI in Redis until expiry.
    Kong checks this Redis set on each request via a custom plugin.
    """
    redis: aioredis.Redis = request.app.state.redis
    ttl = max(claims.exp - int(__import__("time").time()), 1)
    await redis.setex(f"revoked_jti:{claims.jti}", ttl, "1")
    log.info("auth.logout", user_id=claims.sub, jti=claims.jti)
    return {"status": "logged_out", "jti": claims.jti}


@router.get("/me")
async def get_me(claims: TokenClaims = Depends(get_current_claims)):
    """Return the current user's claims (non-sensitive fields only)."""
    return {
        "user_id": claims.sub,
        "tenant_id": claims.tenant_id,
        "role": claims.role,
        "exp": claims.exp,
    }


@router.post("/authorize", response_model=ABACResponse)
async def authorize(
    req: ABACRequest,
    claims: TokenClaims = Depends(get_current_claims),
):
    """
    Evaluate an ABAC policy decision.
    Called by MCP tool servers and the API before executing sensitive actions.

    The caller provides the action, resource type, and optional column list.
    Returns allow/deny + list of columns to mask.
    """
    # Enforce: callers can only check their own user/tenant (not others')
    if req.user_id != claims.sub or req.tenant_id != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot evaluate policy for a different user or tenant",
        )

    result = _abac.evaluate(req)

    log.info(
        "abac.decision",
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        resource=req.resource_type,
        action=req.action,
        allowed=result.allowed,
    )
    return result


@router.post("/verify")
async def verify_token(request: Request):
    """
    Kong-callable token verification endpoint.
    Called by Kong's auth plugin on every request.
    Returns 200 + claims if valid, 401 if not.
    """
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing token")

    try:
        claims = decode_token(token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # Check revocation list
    redis: aioredis.Redis = request.app.state.redis
    if await redis.exists(f"revoked_jti:{claims.jti}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return {
        "valid": True,
        "user_id": claims.sub,
        "tenant_id": claims.tenant_id,
        "role": claims.role,
        "exp": claims.exp,
    }
