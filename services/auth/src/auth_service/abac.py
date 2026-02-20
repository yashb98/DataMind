"""
ABAC Policy Engine — Attribute-Based Access Control.

Design:
  SRP: Only evaluates access policy — no auth, no token management.
  OCP: New rules added to _POLICY_RULES dict without modifying evaluate().
  ISP: ABACRequest only contains the attributes needed for decisions.

Policy Matrix (simplified):
  admin         → full access to everything in their tenant
  data_scientist → read/write datasets, models, notebooks; no admin
  analyst       → read datasets + dashboards; write dashboards; no model deploy
  viewer        → read dashboards only; no datasets, no models
  dpo           → read GDPR artifacts + DSR; no data access
  worker        → read/execute datasets assigned to them; no admin
"""
import structlog

from auth_service.models import ABACRequest, ABACResponse, SensitivityLevel, UserRole

log = structlog.get_logger(__name__)


# ---- Allowed action matrix -------------------------------------------------
# (role, resource_type) → set of allowed actions
_ALLOW_MATRIX: dict[tuple[UserRole, str], set[str]] = {
    # Admin — full tenant control
    (UserRole.ADMIN, "*"):          {"read", "write", "delete", "execute", "admin"},

    # Data Scientist — models, datasets, notebooks, no billing/admin
    (UserRole.DATA_SCIENTIST, "dataset"):   {"read", "write"},
    (UserRole.DATA_SCIENTIST, "model"):     {"read", "write", "execute"},
    (UserRole.DATA_SCIENTIST, "notebook"):  {"read", "write", "execute"},
    (UserRole.DATA_SCIENTIST, "dashboard"): {"read", "write"},
    (UserRole.DATA_SCIENTIST, "report"):    {"read"},
    (UserRole.DATA_SCIENTIST, "worker"):    {"read"},

    # Analyst — read data, build dashboards, no models/admin
    (UserRole.ANALYST, "dataset"):   {"read"},
    (UserRole.ANALYST, "dashboard"): {"read", "write"},
    (UserRole.ANALYST, "report"):    {"read"},
    (UserRole.ANALYST, "worker"):    {"read"},

    # Viewer — read-only dashboards and reports
    (UserRole.VIEWER, "dashboard"): {"read"},
    (UserRole.VIEWER, "report"):    {"read"},

    # DPO — GDPR artifacts only
    (UserRole.DPO, "gdpr"):         {"read", "write", "execute"},
    (UserRole.DPO, "audit_log"):    {"read"},
    (UserRole.DPO, "dsr"):          {"read", "write", "execute"},

    # Worker (Digital Workers) — datasets + execution only
    (UserRole.WORKER, "dataset"):   {"read"},
    (UserRole.WORKER, "dashboard"): {"read", "write"},
    (UserRole.WORKER, "report"):    {"read", "write"},
    (UserRole.WORKER, "model"):     {"read", "execute"},
}

# Sensitivity-gated columns: if resource sensitivity ≥ threshold,
# these columns must be masked for the given role.
_COLUMN_SENSITIVITY_GATES: dict[UserRole, SensitivityLevel] = {
    UserRole.ADMIN:          SensitivityLevel.RESTRICTED,  # admin sees everything < RESTRICTED
    UserRole.DATA_SCIENTIST: SensitivityLevel.CONFIDENTIAL,
    UserRole.ANALYST:        SensitivityLevel.INTERNAL,
    UserRole.VIEWER:         SensitivityLevel.PUBLIC,
    UserRole.DPO:            SensitivityLevel.RESTRICTED,  # DPO can see PII for DSR
    UserRole.WORKER:         SensitivityLevel.CONFIDENTIAL,
}

_SENSITIVITY_ORDER = [
    SensitivityLevel.PUBLIC,
    SensitivityLevel.INTERNAL,
    SensitivityLevel.CONFIDENTIAL,
    SensitivityLevel.RESTRICTED,
]


def _sensitivity_rank(s: SensitivityLevel) -> int:
    return _SENSITIVITY_ORDER.index(s)


def _is_action_allowed(role: UserRole, resource_type: str, action: str) -> bool:
    # Admin wildcard
    admin_key = (UserRole.ADMIN, "*")
    if role == UserRole.ADMIN and action in _ALLOW_MATRIX.get(admin_key, set()):
        return True

    key = (role, resource_type)
    allowed_actions = _ALLOW_MATRIX.get(key, set())
    return action in allowed_actions


def _compute_column_masks(
    role: UserRole,
    resource_sensitivity: SensitivityLevel,
    column_names: list[str],
) -> tuple[list[str], list[str]]:
    """Returns (masked_columns, allowed_columns)."""
    if not column_names:
        return [], []

    gate = _COLUMN_SENSITIVITY_GATES.get(role, SensitivityLevel.PUBLIC)
    if _sensitivity_rank(resource_sensitivity) < _sensitivity_rank(gate):
        # Resource sensitivity is below the role's gate — all columns visible
        return [], list(column_names)

    # Simple heuristic: mask obviously sensitive column names
    # In production, this would use the Presidio PII metadata from PostgreSQL
    pii_column_patterns = {
        "email", "phone", "address", "ssn", "passport", "dob", "birth",
        "salary", "income", "credit_card", "national_id", "ip_address",
        "name", "firstname", "lastname", "surname",
    }
    masked, allowed = [], []
    for col in column_names:
        col_lower = col.lower()
        if any(pat in col_lower for pat in pii_column_patterns):
            masked.append(col)
        else:
            allowed.append(col)

    return masked, allowed


class ABACPolicyEngine:
    """
    SRP: Evaluates ABAC policy only.
    Stateless — all decisions from policy rules + request attributes.
    """

    def evaluate(self, req: ABACRequest) -> ABACResponse:
        # Check action permission
        allowed = _is_action_allowed(req.role, req.resource_type, req.action)

        if not allowed:
            reason = (
                f"Role '{req.role.value}' is not permitted to '{req.action}' "
                f"on resource type '{req.resource_type}'"
            )
            log.info(
                "abac.denied",
                user_id=req.user_id,
                tenant_id=req.tenant_id,
                role=req.role,
                action=req.action,
                resource=req.resource_type,
            )
            return ABACResponse(allowed=False, reason=reason)

        # Compute column-level masks
        masked, visible = _compute_column_masks(
            req.role, req.resource_sensitivity, req.column_names
        )

        reason = (
            f"Allowed: role='{req.role.value}', action='{req.action}', "
            f"resource='{req.resource_type}'"
        )
        if masked:
            reason += f" | {len(masked)} column(s) masked for sensitivity={req.resource_sensitivity.value}"

        log.debug(
            "abac.allowed",
            user_id=req.user_id,
            role=req.role,
            action=req.action,
            masked_count=len(masked),
        )

        return ABACResponse(
            allowed=True,
            reason=reason,
            masked_columns=masked,
            allowed_columns=visible,
        )
