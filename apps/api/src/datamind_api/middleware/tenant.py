"""
Tenant Isolation Middleware — Day 3.

Extracts tenant context injected by Kong (X-Tenant-ID header from JWT consumer)
and makes it available throughout the request lifecycle via contextvars.

Design:
  SRP: Only sets up tenant context — no auth logic, no business logic.
  DIP: Depends on header names (config), not on Kong internals directly.

Flow:
  Kong verifies JWT → extracts consumer.custom_id (= tenant_id)
       → injects X-Tenant-ID header → this middleware reads it
       → all downstream handlers access tenant via get_current_tenant()
"""
import uuid
from contextvars import ContextVar
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

log = structlog.get_logger(__name__)

# ---- Context variable — available anywhere in the call stack ---------------
_current_tenant: ContextVar["TenantContext | None"] = ContextVar(
    "_current_tenant", default=None
)


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    role: str
    request_id: str


def get_current_tenant() -> TenantContext:
    """
    Retrieve tenant context from the current async context.
    Raises RuntimeError if called outside a request context.
    """
    ctx = _current_tenant.get()
    if ctx is None:
        raise RuntimeError("No tenant context — was TenantMiddleware applied?")
    return ctx


def get_tenant_id() -> str:
    """Convenience: just the tenant_id string."""
    return get_current_tenant().tenant_id


# ---- Paths that bypass tenant requirement (public endpoints) ---------------
_PUBLIC_PATHS = {
    "/health/liveness",
    "/health/readiness",
    "/auth/login",
    "/auth/verify",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
}


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """
    Reads Kong-injected headers to establish tenant context.

    Headers injected by Kong request-transformer plugin:
      X-Tenant-ID    — UUID of the authenticated tenant (from JWT consumer.custom_id)
      X-Kong-Consumer — username of the Kong consumer
      X-Request-ID   — correlation ID (injected by Kong correlation-id plugin)

    The user_id and role come from the JWT claims which Kong validates.
    In this middleware we read the pre-validated headers — we trust Kong
    has already verified the JWT signature.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip auth for public paths
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID")
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # In dev mode without Kong, allow a fallback header for testing
        if not tenant_id:
            tenant_id = request.headers.get("X-Dev-Tenant-ID")

        if not tenant_id:
            # Not proxied through Kong and no dev override
            if _is_dev_bypass(request):
                tenant_id = "00000000-0000-0000-0000-000000000001"  # demo tenant
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing tenant context. Ensure request is routed through Kong.",
                )

        # Validate UUID format
        try:
            uuid.UUID(tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid X-Tenant-ID format: {tenant_id!r}",
            )

        ctx = TenantContext(
            tenant_id=tenant_id,
            user_id=request.headers.get("X-User-ID", "unknown"),
            role=request.headers.get("X-User-Role", "analyst"),
            request_id=request_id,
        )

        token = _current_tenant.set(ctx)

        # Bind to structlog context for all log lines in this request
        structlog.contextvars.bind_contextvars(
            tenant_id=tenant_id,
            request_id=request_id,
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _current_tenant.reset(token)
            structlog.contextvars.clear_contextvars()


def _is_dev_bypass(request: Request) -> bool:
    """Allow direct API access in development without Kong."""
    from datamind_api.config import settings
    return settings.env == "development"
