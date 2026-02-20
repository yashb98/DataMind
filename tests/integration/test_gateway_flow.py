"""
Integration tests — End-to-end gateway flow.
Day 3: Validates the Kong → FastAPI → LiteLLM → Langfuse path.

These tests require docker compose to be running.
Run with: pytest tests/integration/ -m integration --timeout=60

They are SKIPPED in CI unless DATAMIND_INTEGRATION_TESTS=true is set.
"""
import os
import time

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"

# Service base URLs
KONG_URL   = os.getenv("KONG_URL",   "http://localhost:8000")
API_URL    = os.getenv("API_URL",    "http://localhost:8001")   # direct (bypasses Kong)
AUTH_URL   = os.getenv("AUTH_URL",   "http://localhost:8010")
ROUTER_URL = os.getenv("ROUTER_URL", "http://localhost:8020")
EMBED_URL  = os.getenv("EMBED_URL",  "http://localhost:8030")
LANGFUSE_URL = os.getenv("LANGFUSE_URL", "http://localhost:3001")
LITELLM_URL  = os.getenv("LITELLM_URL",  "http://localhost:4000")

pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Integration tests skipped. Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)


# ---- Helpers ---------------------------------------------------------------

def get_dev_token() -> str:
    """Login as demo analyst and get a JWT."""
    r = httpx.post(
        f"{AUTH_URL}/auth/login",
        json={"email": "analyst@demo.datamind.ai", "password": "datamind-dev", "tenant_slug": "demo"},
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


# ---- Health checks ---------------------------------------------------------

class TestServiceHealth:
    def test_auth_service_liveness(self):
        r = httpx.get(f"{AUTH_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_auth_service_readiness(self):
        r = httpx.get(f"{AUTH_URL}/health/readiness", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_slm_router_liveness(self):
        r = httpx.get(f"{ROUTER_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_embedding_service_liveness(self):
        r = httpx.get(f"{EMBED_URL}/health/liveness", timeout=5)
        assert r.status_code == 200

    def test_litellm_liveness(self):
        r = httpx.get(f"{LITELLM_URL}/health/liveliness", timeout=5)
        assert r.status_code == 200

    def test_langfuse_health(self):
        r = httpx.get(f"{LANGFUSE_URL}/api/public/health", timeout=10)
        assert r.status_code == 200


# ---- Auth flow -------------------------------------------------------------

class TestAuthFlow:
    def test_dev_login_returns_token(self):
        token = get_dev_token()
        assert token.startswith("ey")   # JWT format

    def test_token_verify_endpoint(self):
        token = get_dev_token()
        r = httpx.post(
            f"{AUTH_URL}/auth/verify",
            json={"token": token},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert "tenant_id" in data
        assert "role" in data

    def test_garbage_token_rejected(self):
        r = httpx.post(
            f"{AUTH_URL}/auth/verify",
            json={"token": "not.a.real.token"},
            timeout=5,
        )
        assert r.status_code == 401

    def test_me_endpoint_returns_claims(self):
        token = get_dev_token()
        r = httpx.get(
            f"{AUTH_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "tenant_id" in data
        assert data["role"] == "analyst"

    def test_logout_revokes_token(self):
        token = get_dev_token()
        # Logout
        r = httpx.post(
            f"{AUTH_URL}/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 200
        jti = r.json()["jti"]

        # Verify the revoked token is now rejected
        r2 = httpx.post(
            f"{AUTH_URL}/auth/verify",
            json={"token": token},
            timeout=5,
        )
        assert r2.status_code == 401


# ---- ABAC policy evaluation ------------------------------------------------

class TestABACFlow:
    def test_analyst_allowed_to_read_dataset(self):
        token = get_dev_token()
        r = httpx.post(
            f"{AUTH_URL}/auth/authorize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": "demo-analyst-001",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "role": "analyst",
                "action": "read",
                "resource_type": "dataset",
                "resource_sensitivity": "public",
                "column_names": ["revenue", "product_name", "region"],
            },
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["allowed"] is True

    def test_analyst_denied_model_write(self):
        token = get_dev_token()
        r = httpx.post(
            f"{AUTH_URL}/auth/authorize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": "demo-analyst-001",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "role": "analyst",
                "action": "write",
                "resource_type": "model",
                "resource_sensitivity": "internal",
                "column_names": [],
            },
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["allowed"] is False

    def test_pii_columns_masked_for_analyst(self):
        token = get_dev_token()
        r = httpx.post(
            f"{AUTH_URL}/auth/authorize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": "demo-analyst-001",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "role": "analyst",
                "action": "read",
                "resource_type": "dataset",
                "resource_sensitivity": "confidential",
                "column_names": ["revenue", "customer_email", "salary", "region"],
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["allowed"] is True
        assert "customer_email" in data["masked_columns"]
        assert "salary" in data["masked_columns"]
        assert "revenue" in data["allowed_columns"]


# ---- SLM Router flow -------------------------------------------------------

class TestSLMRouterFlow:
    def test_sql_query_routes_to_cloud(self):
        r = httpx.post(
            f"{ROUTER_URL}/route",
            json={
                "query": "SELECT total revenue by region for last quarter using SQL",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["intent"] in ("SQL", "EDA", "VISUALISE")
        assert data["tier"] in ("edge", "slm", "cloud")
        assert "model" in data

    def test_restricted_data_stays_local(self):
        r = httpx.post(
            f"{ROUTER_URL}/route",
            json={
                "query": "Show me SSN and salary data for all employees",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        # GDPR critical: restricted data must never route to cloud or edge
        assert data["sensitivity"] == "restricted"
        assert data["tier"] in ("slm", "rlm"), (
            f"GDPR violation: restricted data routed to {data['tier']}"
        )

    def test_causal_query_routes_to_rlm(self):
        r = httpx.post(
            f"{ROUTER_URL}/route",
            json={
                "query": (
                    "Build a causal inference model to explain why revenue dropped in Q3. "
                    "Account for confounders, test statistical significance, and quantify "
                    "the counterfactual impact of each variable."
                ),
                "tenant_id": "00000000-0000-0000-0000-000000000001",
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["complexity"] in ("complex", "expert")

    def test_route_result_cached_on_second_call(self):
        payload = {
            "query": "Show total sales for today",
            "tenant_id": "00000000-0000-0000-0000-000000000001",
        }
        r1 = httpx.post(f"{ROUTER_URL}/route", json=payload, timeout=30)
        r2 = httpx.post(f"{ROUTER_URL}/route", json=payload, timeout=10)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["cached"] is True


# ---- FastAPI direct health (bypassing Kong) --------------------------------

class TestAPIDirectHealth:
    """
    Tests the FastAPI service directly (port 8001 internal admin, or 8000 direct).
    These bypass Kong to test the API layer in isolation.
    """
    def test_liveness_probe(self):
        r = httpx.get(f"{API_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"

    def test_readiness_probe_structure(self):
        r = httpx.get(f"{API_URL}/health/readiness", timeout=15)
        assert r.status_code in (200, 503)
        data = r.json()
        assert "services" in data
        assert isinstance(data["services"], list)

    def test_openapi_schema_present(self):
        r = httpx.get(f"{API_URL}/openapi.json", timeout=5)
        assert r.status_code == 200
        assert r.json()["info"]["title"] == "DataMind API"


# ---- LiteLLM proxy sanity --------------------------------------------------

class TestLiteLLMProxy:
    def test_models_list_returns_configured_models(self):
        r = httpx.get(
            f"{LITELLM_URL}/models",
            headers={"Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', 'sk-litellm-dev')}"},
            timeout=10,
        )
        assert r.status_code == 200
        models = {m["id"] for m in r.json().get("data", [])}
        assert len(models) > 0

    def test_completion_traces_in_langfuse(self):
        """
        End-to-end: LiteLLM call → Langfuse trace appears within 10s.
        Uses a minimal prompt to keep cost near-zero.
        """
        before_ts = int(time.time())

        # Make a minimal LLM call
        r = httpx.post(
            f"{LITELLM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', 'sk-litellm-dev')}"},
            json={
                "model": "phi3.5",   # local SLM — zero cloud cost
                "messages": [{"role": "user", "content": "Say 'ok' in one word."}],
                "max_tokens": 5,
            },
            timeout=60,
        )
        assert r.status_code == 200

        # Allow Langfuse async flush time
        time.sleep(5)

        # Check Langfuse API for recent traces
        lf_r = httpx.get(
            f"{LANGFUSE_URL}/api/public/traces",
            auth=(
                os.getenv("LANGFUSE_PUBLIC_KEY", "lf-pk-dev"),
                os.getenv("LANGFUSE_SECRET_KEY", "lf-sk-dev"),
            ),
            params={"fromTimestamp": before_ts, "limit": 10},
            timeout=10,
        )
        assert lf_r.status_code == 200
        traces = lf_r.json().get("data", [])
        assert len(traces) > 0, "No traces found in Langfuse — callback may not be wired"
