"""
JWT handler unit tests.
Tests token creation, decoding, claim structure, and expiry.
"""
import time

import pytest
from jose import JWTError

from auth_service.jwt_handler import create_access_token, decode_token
from auth_service.models import UserRole


class TestJWTCreation:
    def test_creates_valid_token(self):
        token, claims = create_access_token(
            user_id="user-123",
            tenant_id="tenant-456",
            role=UserRole.ANALYST,
            email="analyst@test.com",
            kong_kid="test-key",
        )
        assert isinstance(token, str)
        assert len(token) > 50
        assert claims.sub == "user-123"
        assert claims.tenant_id == "tenant-456"
        assert claims.role == UserRole.ANALYST

    def test_email_is_pseudonymised(self):
        _, claims = create_access_token(
            user_id="u1",
            tenant_id="t1",
            role=UserRole.VIEWER,
            email="real.email@example.com",
            kong_kid="k1",
        )
        # email_hash must NOT contain the original email
        assert "real.email@example.com" not in claims.email_hash
        assert "@" not in claims.email_hash
        assert len(claims.email_hash) == 32  # truncated HMAC-SHA256

    def test_token_has_required_kong_fields(self):
        _, claims = create_access_token(
            user_id="u1", tenant_id="t1",
            role=UserRole.ADMIN, email="a@b.com", kong_kid="my-key",
        )
        assert claims.kid == "my-key"    # Kong uses kid to look up secret
        assert claims.jti != ""          # JTI for revocation
        assert claims.exp > int(time.time())
        assert claims.nbf <= int(time.time())

    def test_different_tenants_produce_different_email_hashes(self):
        _, claims1 = create_access_token(
            user_id="u1", tenant_id="tenant-A",
            role=UserRole.ANALYST, email="same@email.com", kong_kid="k",
        )
        _, claims2 = create_access_token(
            user_id="u1", tenant_id="tenant-B",
            role=UserRole.ANALYST, email="same@email.com", kong_kid="k",
        )
        # Email hash must be tenant-scoped (prevents cross-tenant correlation)
        assert claims1.email_hash != claims2.email_hash


class TestJWTDecoding:
    def test_decode_valid_token(self):
        token, original = create_access_token(
            user_id="user-xyz", tenant_id="tenant-abc",
            role=UserRole.DATA_SCIENTIST, email="ds@test.com", kong_kid="k",
        )
        decoded = decode_token(token)
        assert decoded.sub == original.sub
        assert decoded.tenant_id == original.tenant_id
        assert decoded.role == original.role

    def test_decode_tampered_token_raises(self):
        token, _ = create_access_token(
            user_id="u", tenant_id="t", role=UserRole.VIEWER,
            email="v@t.com", kong_kid="k",
        )
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_token(tampered)

    def test_decode_garbage_raises(self):
        with pytest.raises(JWTError):
            decode_token("not.a.jwt.token")

    def test_expire_minutes_respected(self):
        token, claims = create_access_token(
            user_id="u", tenant_id="t", role=UserRole.VIEWER,
            email="v@t.com", kong_kid="k", expire_minutes=30,
        )
        now = int(time.time())
        # expiry should be roughly now + 30min (within 5s tolerance)
        assert abs(claims.exp - (now + 1800)) < 5

    def test_max_expire_capped(self):
        """Token lifetime must never exceed jwt_max_expire_minutes."""
        _, claims = create_access_token(
            user_id="u", tenant_id="t", role=UserRole.ADMIN,
            email="a@t.com", kong_kid="k", expire_minutes=99999,
        )
        from auth_service.config import settings
        max_exp = int(time.time()) + (settings.jwt_max_expire_minutes * 60)
        assert claims.exp <= max_exp + 5  # 5s tolerance
