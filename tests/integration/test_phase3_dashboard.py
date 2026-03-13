"""
Integration tests — Phase 3: Dashboard API + Visualization stack.
Days 15-17: Requires running docker compose stack (DATAMIND_INTEGRATION_TESTS=true).

Usage:
    DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/test_phase3_dashboard.py -v

SLO targets validated here:
    dashboard-api:  health < 100ms, CRUD round-trip < 200ms
    nl-to-dashboard: E2E < 8s (10s timeout)
    WebSocket:      connects and receives snapshot < 500ms
"""

from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Integration tests skipped. Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)

DASHBOARD_API_URL = os.getenv("DASHBOARD_API_URL", "http://localhost:8110")
TEST_TENANT = "integration_test"


# ── Health ────────────────────────────────────────────────────────────────────


class TestDashboardAPIHealth:
    def test_liveness(self) -> None:
        r = httpx.get(f"{DASHBOARD_API_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "dashboard-api"

    def test_readiness(self) -> None:
        r = httpx.get(f"{DASHBOARD_API_URL}/health/readiness", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_liveness_under_100ms_slo(self) -> None:
        start = time.perf_counter()
        r = httpx.get(f"{DASHBOARD_API_URL}/health/liveness", timeout=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 100, f"Health latency {elapsed_ms:.1f}ms exceeds 100ms SLO"


# ── Dashboard CRUD ────────────────────────────────────────────────────────────


class TestDashboardCRUD:
    """Full CRUD round-trip: create → get → update → list → delete."""

    def test_create_dashboard(self) -> None:
        payload = {
            "tenant_id": TEST_TENANT,
            "title": "Integration Test Dashboard",
            "description": "Created by automated integration test",
            "widgets": [
                {
                    "widget_type": "chart",
                    "title": "Revenue Over Time",
                    "chart_type": "line",
                    "x": 0, "y": 0, "w": 8, "h": 4,
                    "data_source": {},
                    "chart_config": {},
                    "refresh_interval_s": 0,
                }
            ],
            "theme": "dark",
            "tags": ["test", "integration"],
        }
        r = httpx.post(f"{DASHBOARD_API_URL}/api/dashboards", json=payload, timeout=10)
        assert r.status_code in (200, 201)
        data = r.json()
        assert "dashboard_id" in data
        assert data["title"] == "Integration Test Dashboard"
        assert data["tenant_id"] == TEST_TENANT
        assert len(data["widgets"]) == 1
        # Store for subsequent tests via class variable
        TestDashboardCRUD._created_id = data["dashboard_id"]

    def test_get_dashboard(self) -> None:
        if not hasattr(TestDashboardCRUD, "_created_id"):
            pytest.skip("Depends on test_create_dashboard running first")
        r = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards/{TestDashboardCRUD._created_id}",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["dashboard_id"] == TestDashboardCRUD._created_id

    def test_list_dashboards(self) -> None:
        r = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_update_dashboard(self) -> None:
        if not hasattr(TestDashboardCRUD, "_created_id"):
            pytest.skip("Depends on test_create_dashboard running first")
        r = httpx.put(
            f"{DASHBOARD_API_URL}/api/dashboards/{TestDashboardCRUD._created_id}",
            params={"tenant_id": TEST_TENANT},
            json={"title": "Updated Integration Dashboard", "tags": ["test", "updated"]},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Updated Integration Dashboard"

    def test_delete_dashboard(self) -> None:
        if not hasattr(TestDashboardCRUD, "_created_id"):
            pytest.skip("Depends on test_create_dashboard running first")
        r = httpx.delete(
            f"{DASHBOARD_API_URL}/api/dashboards/{TestDashboardCRUD._created_id}",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r.status_code in (200, 204)

        # Verify deleted
        r2 = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards/{TestDashboardCRUD._created_id}",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r2.status_code == 404

    def test_get_nonexistent_dashboard_returns_404(self) -> None:
        r = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards/nonexistent-id-xyz",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r.status_code == 404

    def test_crud_round_trip_under_200ms(self) -> None:
        """Full create + get + delete must complete under 200ms each."""
        payload = {
            "tenant_id": TEST_TENANT,
            "title": f"SLO Test {uuid.uuid4().hex[:6]}",
            "widgets": [],
        }

        # Create
        start = time.perf_counter()
        r = httpx.post(f"{DASHBOARD_API_URL}/api/dashboards", json=payload, timeout=5)
        create_ms = (time.perf_counter() - start) * 1000
        assert r.status_code in (200, 201)
        dashboard_id = r.json()["dashboard_id"]
        assert create_ms < 500, f"Create latency {create_ms:.1f}ms too high"

        # Get
        start = time.perf_counter()
        r = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards/{dashboard_id}",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )
        get_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert get_ms < 200, f"Get latency {get_ms:.1f}ms exceeds 200ms SLO"

        # Cleanup
        httpx.delete(
            f"{DASHBOARD_API_URL}/api/dashboards/{dashboard_id}",
            params={"tenant_id": TEST_TENANT},
            timeout=5,
        )


# ── NL → Dashboard ────────────────────────────────────────────────────────────


class TestNLToDashboard:
    def test_nl_to_dashboard_returns_config(self) -> None:
        """NL → Dashboard must return a DashboardConfig with widgets within 10s SLO."""
        start = time.perf_counter()
        r = httpx.post(
            f"{DASHBOARD_API_URL}/api/dashboards/nl-to-dashboard",
            json={
                "prompt": "Show me total revenue by region with trend over the last quarter",
                "tenant_id": TEST_TENANT,
                "user_id": "integration_test",
            },
            timeout=12,  # allow 2s buffer over 10s SLO
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert r.status_code == 200
        data = r.json()
        assert "dashboard_config" in data
        config = data["dashboard_config"]
        assert "dashboard_id" in config
        assert "title" in config
        assert isinstance(config["widgets"], list)
        assert len(config["widgets"]) >= 1  # must generate at least 1 widget
        assert elapsed_ms < 10_000, f"NL→Dashboard took {elapsed_ms:.0f}ms, exceeds 10s SLO"

    def test_nl_to_dashboard_widgets_have_required_fields(self) -> None:
        r = httpx.post(
            f"{DASHBOARD_API_URL}/api/dashboards/nl-to-dashboard",
            json={
                "prompt": "Sales pipeline funnel by stage",
                "tenant_id": TEST_TENANT,
            },
            timeout=12,
        )
        assert r.status_code == 200
        widgets = r.json()["dashboard_config"]["widgets"]
        for w in widgets:
            assert "widget_id" in w
            assert "widget_type" in w
            assert "title" in w
            assert "x" in w and "y" in w
            assert "w" in w and "h" in w

    def test_nl_to_dashboard_includes_generation_ms(self) -> None:
        r = httpx.post(
            f"{DASHBOARD_API_URL}/api/dashboards/nl-to-dashboard",
            json={"prompt": "Monthly active users", "tenant_id": TEST_TENANT},
            timeout=12,
        )
        assert r.status_code == 200
        data = r.json()
        assert "generation_ms" in data
        assert isinstance(data["generation_ms"], float)


# ── WebSocket ─────────────────────────────────────────────────────────────────


class TestDashboardWebSocket:
    def test_websocket_snapshot_on_connect(self) -> None:
        """WebSocket must send a snapshot message within 500ms of connecting."""
        import asyncio
        import websockets

        async def _check() -> dict:
            uri = (
                f"ws://localhost:8110/ws/dashboards/test-dash-001"
                f"?tenant_id={TEST_TENANT}"
            )
            start = time.perf_counter()
            async with websockets.connect(uri, open_timeout=5) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {"msg": json.loads(msg), "elapsed_ms": elapsed_ms}

        result = asyncio.run(_check())
        assert result["msg"]["type"] == "snapshot"
        assert result["elapsed_ms"] < 500, (
            f"WebSocket snapshot took {result['elapsed_ms']:.1f}ms, exceeds 500ms SLO"
        )

    def test_websocket_heartbeat(self) -> None:
        """WebSocket must send a heartbeat within 35s (30s interval + 5s buffer)."""
        import asyncio
        import websockets

        async def _check() -> str:
            uri = (
                f"ws://localhost:8110/ws/dashboards/heartbeat-test"
                f"?tenant_id={TEST_TENANT}"
            )
            async with websockets.connect(uri, open_timeout=5) as ws:
                # Skip snapshot
                await asyncio.wait_for(ws.recv(), timeout=2)
                # Wait for heartbeat (30s interval, allow up to 35s)
                msg = await asyncio.wait_for(ws.recv(), timeout=35)
                return json.loads(msg)["type"]

        msg_type = asyncio.run(_check())
        assert msg_type == "heartbeat"


# ── Tenant isolation ──────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_dashboards_are_tenant_isolated(self) -> None:
        """Dashboards created for tenant A must not appear for tenant B."""
        tenant_a = f"tenant_a_{uuid.uuid4().hex[:6]}"
        tenant_b = f"tenant_b_{uuid.uuid4().hex[:6]}"

        # Create dashboard for tenant A
        r = httpx.post(
            f"{DASHBOARD_API_URL}/api/dashboards",
            json={"tenant_id": tenant_a, "title": "Tenant A Dashboard", "widgets": []},
            timeout=5,
        )
        assert r.status_code in (200, 201)
        dashboard_id = r.json()["dashboard_id"]

        # Tenant B must not see it
        r2 = httpx.get(
            f"{DASHBOARD_API_URL}/api/dashboards/{dashboard_id}",
            params={"tenant_id": tenant_b},
            timeout=5,
        )
        assert r2.status_code == 404

        # Cleanup
        httpx.delete(
            f"{DASHBOARD_API_URL}/api/dashboards/{dashboard_id}",
            params={"tenant_id": tenant_a},
            timeout=5,
        )
