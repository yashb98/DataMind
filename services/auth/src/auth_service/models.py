"""Auth service models — JWT claims, ABAC policy, token responses."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    ADMIN          = "admin"
    ANALYST        = "analyst"
    DATA_SCIENTIST = "data_scientist"
    VIEWER         = "viewer"
    DPO            = "dpo"           # Data Protection Officer
    WORKER         = "worker"        # Digital Worker service account


class SensitivityLevel(str, Enum):
    PUBLIC       = "public"
    INTERNAL     = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED   = "restricted"


# ---- JWT Claims (ISP: only the fields needed for auth decisions) -----------
class TokenClaims(BaseModel):
    sub: str            # user_id (UUID string)
    tenant_id: str
    role: UserRole
    email_hash: str     # HMAC pseudonym — never the real email
    exp: int            # Unix timestamp
    nbf: int            # Not before
    iat: int            # Issued at
    kid: str            # Kong JWT key ID (matches consumer)
    jti: str            # JWT ID (for revocation)


# ---- Token responses -------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int         # seconds
    tenant_id: str
    role: UserRole


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: str        # determines which tenant DB schema


# ---- ABAC Policy -----------------------------------------------------------
class ABACRequest(BaseModel):
    user_id: str
    tenant_id: str
    role: UserRole
    action: str             # read | write | delete | execute
    resource_type: str      # dataset | dashboard | worker | report | admin
    resource_id: str | None = None
    resource_sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC
    column_names: list[str] = Field(default_factory=list)  # for column-level checks


class ABACResponse(BaseModel):
    allowed: bool
    reason: str
    masked_columns: list[str] = Field(default_factory=list)  # columns to mask in response
    allowed_columns: list[str] = Field(default_factory=list)  # columns user can see


# ---- Tenant ----------------------------------------------------------------
class TenantInfo(BaseModel):
    tenant_id: str
    name: str
    plan_tier: str
    data_region: str
    gdpr_enabled: bool
