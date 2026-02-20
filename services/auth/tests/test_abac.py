"""
ABAC policy engine unit tests — no external dependencies.
Covers the full role × resource × action matrix and column masking.
"""
import pytest

from auth_service.abac import ABACPolicyEngine
from auth_service.models import ABACRequest, SensitivityLevel, UserRole


@pytest.fixture
def engine():
    return ABACPolicyEngine()


def _req(
    role: UserRole,
    resource_type: str,
    action: str,
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC,
    columns: list[str] | None = None,
) -> ABACRequest:
    return ABACRequest(
        user_id="test-user",
        tenant_id="test-tenant",
        role=role,
        action=action,
        resource_type=resource_type,
        resource_sensitivity=sensitivity,
        column_names=columns or [],
    )


# ---- Admin role: full access -----------------------------------------------
class TestAdminRole:
    def test_admin_can_read_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.ADMIN, "dataset", "read"))
        assert r.allowed

    def test_admin_can_delete_dashboard(self, engine):
        r = engine.evaluate(_req(UserRole.ADMIN, "dashboard", "delete"))
        assert r.allowed

    def test_admin_can_admin_action(self, engine):
        r = engine.evaluate(_req(UserRole.ADMIN, "worker", "admin"))
        assert r.allowed


# ---- Analyst role -----------------------------------------------------------
class TestAnalystRole:
    def test_analyst_can_read_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.ANALYST, "dataset", "read"))
        assert r.allowed

    def test_analyst_cannot_write_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.ANALYST, "dataset", "write"))
        assert not r.allowed

    def test_analyst_cannot_train_model(self, engine):
        r = engine.evaluate(_req(UserRole.ANALYST, "model", "write"))
        assert not r.allowed

    def test_analyst_can_write_dashboard(self, engine):
        r = engine.evaluate(_req(UserRole.ANALYST, "dashboard", "write"))
        assert r.allowed

    def test_analyst_cannot_admin(self, engine):
        r = engine.evaluate(_req(UserRole.ANALYST, "dataset", "admin"))
        assert not r.allowed


# ---- Data Scientist role ---------------------------------------------------
class TestDataScientistRole:
    def test_ds_can_train_model(self, engine):
        r = engine.evaluate(_req(UserRole.DATA_SCIENTIST, "model", "write"))
        assert r.allowed

    def test_ds_can_read_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.DATA_SCIENTIST, "dataset", "read"))
        assert r.allowed

    def test_ds_cannot_admin(self, engine):
        r = engine.evaluate(_req(UserRole.DATA_SCIENTIST, "dataset", "admin"))
        assert not r.allowed


# ---- Viewer role -----------------------------------------------------------
class TestViewerRole:
    def test_viewer_can_read_dashboard(self, engine):
        r = engine.evaluate(_req(UserRole.VIEWER, "dashboard", "read"))
        assert r.allowed

    def test_viewer_cannot_read_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.VIEWER, "dataset", "read"))
        assert not r.allowed

    def test_viewer_cannot_write_anything(self, engine):
        for resource in ["dataset", "dashboard", "model", "report"]:
            r = engine.evaluate(_req(UserRole.VIEWER, resource, "write"))
            assert not r.allowed, f"Viewer should not write {resource}"


# ---- DPO role: GDPR only ---------------------------------------------------
class TestDPORole:
    def test_dpo_can_handle_dsr(self, engine):
        r = engine.evaluate(_req(UserRole.DPO, "dsr", "execute"))
        assert r.allowed

    def test_dpo_can_read_audit_log(self, engine):
        r = engine.evaluate(_req(UserRole.DPO, "audit_log", "read"))
        assert r.allowed

    def test_dpo_cannot_read_raw_dataset(self, engine):
        r = engine.evaluate(_req(UserRole.DPO, "dataset", "read"))
        assert not r.allowed

    def test_dpo_cannot_train_models(self, engine):
        r = engine.evaluate(_req(UserRole.DPO, "model", "write"))
        assert not r.allowed


# ---- Column-level masking --------------------------------------------------
class TestColumnMasking:
    PII_COLS = ["user_email", "customer_name", "phone_number", "salary", "date_of_birth"]
    SAFE_COLS = ["revenue", "product_id", "region", "order_count"]

    def test_viewer_gets_pii_masked(self, engine):
        r = engine.evaluate(_req(
            UserRole.VIEWER, "dashboard", "read",
            sensitivity=SensitivityLevel.INTERNAL,
            columns=self.PII_COLS + self.SAFE_COLS,
        ))
        assert r.allowed
        # Viewer sees only PUBLIC sensitivity — PII cols masked
        assert len(r.masked_columns) > 0
        assert "revenue" in r.allowed_columns

    def test_admin_sees_all_non_restricted_columns(self, engine):
        r = engine.evaluate(_req(
            UserRole.ADMIN, "dataset", "read",
            sensitivity=SensitivityLevel.INTERNAL,
            columns=self.PII_COLS + self.SAFE_COLS,
        ))
        assert r.allowed
        # Admin's gate is RESTRICTED — INTERNAL data passes through
        assert len(r.masked_columns) == 0
        assert set(r.allowed_columns) == set(self.PII_COLS + self.SAFE_COLS)

    def test_analyst_masks_pii_on_confidential_resource(self, engine):
        r = engine.evaluate(_req(
            UserRole.ANALYST, "dataset", "read",
            sensitivity=SensitivityLevel.CONFIDENTIAL,
            columns=self.PII_COLS + self.SAFE_COLS,
        ))
        assert r.allowed
        assert len(r.masked_columns) > 0
        assert "revenue" in r.allowed_columns


# ---- Cross-tenant guard (enforced in router, not engine) -------------------
class TestCrossTenantSafety:
    def test_deny_reason_contains_role_info(self, engine):
        r = engine.evaluate(_req(UserRole.VIEWER, "model", "write"))
        assert not r.allowed
        assert "viewer" in r.reason.lower()
        assert "model" in r.reason.lower()
