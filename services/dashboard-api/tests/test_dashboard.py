"""
Dashboard API Tests — Unit tests for models, parsers, and helper functions.
Day 15: Phase 3 — Verification of dashboard data models and NL parsing logic.

Coverage target: ≥80%
"""

from __future__ import annotations

import json

import pytest

from dashboard_api.models import (
    DashboardConfig,
    NLToDashboardRequest,
    WidgetConfig,
)
from dashboard_api.routers.nl_dashboard import (
    _extract_title,
    _generate_default_widgets,
    _parse_orchestration_response,
)


# ── Model Tests ───────────────────────────────────────────────────────────────


class TestWidgetConfig:
    """Tests for WidgetConfig model defaults and validation."""

    def test_widget_config_defaults(self) -> None:
        """WidgetConfig should auto-generate a short widget_id and set sensible defaults."""
        widget = WidgetConfig(widget_type="chart", title="Test Chart")
        assert widget.widget_id is not None
        assert len(widget.widget_id) == 8
        assert widget.x == 0
        assert widget.y == 0
        assert widget.w == 6
        assert widget.h == 4
        assert widget.chart_type is None
        assert widget.data_source == {}
        assert widget.chart_config == {}
        assert widget.refresh_interval_s == 0

    def test_widget_config_explicit_values(self) -> None:
        """WidgetConfig should store explicitly provided values unchanged."""
        widget = WidgetConfig(
            widget_type="metric",
            title="Revenue",
            chart_type="gauge",
            x=6,
            y=2,
            w=3,
            h=2,
            refresh_interval_s=60,
        )
        assert widget.widget_type == "metric"
        assert widget.chart_type == "gauge"
        assert widget.x == 6
        assert widget.y == 2
        assert widget.w == 3
        assert widget.h == 2
        assert widget.refresh_interval_s == 60

    def test_widget_ids_are_unique(self) -> None:
        """Each WidgetConfig should get a unique widget_id."""
        w1 = WidgetConfig(widget_type="chart", title="A")
        w2 = WidgetConfig(widget_type="chart", title="B")
        assert w1.widget_id != w2.widget_id


class TestDashboardConfig:
    """Tests for DashboardConfig model auto-generation and structure."""

    def test_dashboard_config_auto_id(self) -> None:
        """DashboardConfig should auto-generate a UUID dashboard_id."""
        cfg = DashboardConfig(tenant_id="tenant-1", title="My Dashboard")
        assert cfg.dashboard_id is not None
        assert len(cfg.dashboard_id) == 36  # full UUID
        assert cfg.theme == "dark"
        assert cfg.cols == 12
        assert cfg.row_height == 80
        assert cfg.created_by == "system"
        assert cfg.widgets == []
        assert cfg.tags == []

    def test_dashboard_config_with_widgets(self) -> None:
        """DashboardConfig should store nested WidgetConfig objects."""
        widgets = [
            WidgetConfig(widget_type="chart", title="Sales", chart_type="bar"),
            WidgetConfig(widget_type="metric", title="Total"),
        ]
        cfg = DashboardConfig(
            tenant_id="tenant-2",
            title="Sales Dashboard",
            widgets=widgets,
        )
        assert len(cfg.widgets) == 2
        assert cfg.widgets[0].title == "Sales"
        assert cfg.widgets[1].title == "Total"

    def test_dashboard_config_serialises_to_json(self) -> None:
        """DashboardConfig should serialise to JSON without errors."""
        cfg = DashboardConfig(
            tenant_id="t1",
            title="Test",
            widgets=[WidgetConfig(widget_type="chart", title="Chart")],
        )
        data = cfg.model_dump_json()
        parsed = json.loads(data)
        assert parsed["tenant_id"] == "t1"
        assert len(parsed["widgets"]) == 1

    def test_two_dashboards_have_different_ids(self) -> None:
        """Each DashboardConfig should have a unique auto-generated ID."""
        d1 = DashboardConfig(tenant_id="t1", title="A")
        d2 = DashboardConfig(tenant_id="t1", title="B")
        assert d1.dashboard_id != d2.dashboard_id


class TestNLToDashboardRequest:
    """Tests for NLToDashboardRequest validation."""

    def test_nl_to_dashboard_request(self) -> None:
        """NLToDashboardRequest should parse prompt and tenant_id correctly."""
        req = NLToDashboardRequest(
            prompt="Show me monthly revenue by region",
            tenant_id="tenant-abc",
        )
        assert req.prompt == "Show me monthly revenue by region"
        assert req.tenant_id == "tenant-abc"
        assert req.user_id == "system"
        assert req.context == {}

    def test_nl_to_dashboard_request_custom_user(self) -> None:
        """NLToDashboardRequest should accept custom user_id and context."""
        req = NLToDashboardRequest(
            prompt="Analyse churn",
            tenant_id="tenant-xyz",
            user_id="analyst@example.com",
            context={"schema": "sales_db"},
        )
        assert req.user_id == "analyst@example.com"
        assert req.context == {"schema": "sales_db"}


# ── Parser Tests ──────────────────────────────────────────────────────────────


class TestParseOrchestrationResponse:
    """Tests for _parse_orchestration_response logic."""

    def test_empty_response_returns_defaults(self) -> None:
        """Empty task_data should trigger default widget generation."""
        widgets, reasoning, queries = _parse_orchestration_response(
            {"state": "failed", "artifacts": []},
            "Show sales data",
        )
        assert len(widgets) >= 1
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
        assert isinstance(queries, list)

    def test_extracts_json_from_text(self) -> None:
        """Should parse JSON embedded in artifact text and build WidgetConfig list."""
        payload = {
            "title": "Revenue Dashboard",
            "description": "Monthly revenue overview",
            "widgets": [
                {
                    "widget_type": "chart",
                    "title": "Revenue Trend",
                    "chart_type": "line",
                    "x": 0,
                    "y": 0,
                    "w": 12,
                    "h": 4,
                }
            ],
            "suggested_queries": ["SELECT month, SUM(revenue) FROM sales GROUP BY month"],
        }
        task_data = {
            "artifacts": [
                {
                    "parts": [
                        {
                            "type": "text",
                            "text": f"Here is the config: {json.dumps(payload)}",
                        }
                    ]
                }
            ]
        }
        widgets, reasoning, queries = _parse_orchestration_response(task_data, "revenue")
        assert len(widgets) == 1
        assert widgets[0].title == "Revenue Trend"
        assert widgets[0].chart_type == "line"
        assert reasoning == "Monthly revenue overview"
        assert len(queries) == 1

    def test_malformed_json_falls_back_to_defaults(self) -> None:
        """Malformed JSON in artifact text should fall back to default widgets."""
        task_data = {
            "artifacts": [
                {"parts": [{"type": "text", "text": "Here is the config: {invalid json}"}]}
            ]
        }
        widgets, _, _ = _parse_orchestration_response(task_data, "show metrics")
        # Should not raise — must return default widgets
        assert len(widgets) >= 1

    def test_no_artifacts_key_falls_back_to_defaults(self) -> None:
        """Missing artifacts key should gracefully fall back to defaults."""
        widgets, reasoning, queries = _parse_orchestration_response({}, "sales breakdown")
        assert len(widgets) >= 1


# ── Default Widget Generation Tests ──────────────────────────────────────────


class TestGenerateDefaultWidgets:
    """Tests for _generate_default_widgets keyword-based logic."""

    def test_revenue_prompt_includes_line_and_gauge(self) -> None:
        """Revenue-related prompts should produce a line chart and a gauge metric."""
        widgets = _generate_default_widgets("Show me total revenue by quarter")
        types = {w.chart_type for w in widgets}
        assert "line" in types
        assert "gauge" in types

    def test_sales_prompt_triggers_revenue_widgets(self) -> None:
        """Prompt containing 'sales' should match the revenue keyword branch."""
        widgets = _generate_default_widgets("Daily sales performance")
        assert any(w.chart_type == "line" for w in widgets)

    def test_distribution_prompt_includes_pie(self) -> None:
        """Prompt containing 'distribution' should add a pie chart widget."""
        widgets = _generate_default_widgets("Show distribution by region")
        chart_types = [w.chart_type for w in widgets]
        assert "pie" in chart_types

    def test_trend_prompt_includes_line(self) -> None:
        """Prompt containing 'trend' should add a line chart widget."""
        widgets = _generate_default_widgets("Trend analysis of user growth")
        chart_types = [w.chart_type for w in widgets]
        assert "line" in chart_types

    def test_table_prompt_includes_table_widget(self) -> None:
        """Prompt containing 'table' should add a table widget."""
        widgets = _generate_default_widgets("Show a table of all transactions")
        widget_types = [w.widget_type for w in widgets]
        assert "table" in widget_types

    def test_fallback_always_returns_widgets(self) -> None:
        """Any unrecognised prompt should still produce at least 3 default widgets."""
        widgets = _generate_default_widgets("xyzzy unknown domain metric")
        assert len(widgets) == 3
        chart_types = {w.chart_type for w in widgets}
        assert "line" in chart_types
        assert "bar" in chart_types
        assert "pie" in chart_types

    def test_widgets_have_valid_grid_positions(self) -> None:
        """All generated widgets must have non-negative grid positions."""
        widgets = _generate_default_widgets("some unrecognised prompt about data")
        for w in widgets:
            assert w.x >= 0
            assert w.y >= 0
            assert w.w > 0
            assert w.h > 0


# ── Title Extraction Tests ────────────────────────────────────────────────────


class TestExtractTitle:
    """Tests for _extract_title prompt → title conversion."""

    def test_short_prompt(self) -> None:
        """Short prompts should be title-cased and suffixed with 'Dashboard'."""
        title = _extract_title("sales by region")
        assert title.endswith("Dashboard")
        assert "Sales" in title
        assert "Region" in title

    def test_long_prompt_truncated(self) -> None:
        """Prompts longer than 6 words should be truncated to 6 words."""
        long_prompt = "show me all the revenue data by region and product category"
        title = _extract_title(long_prompt)
        # Should only use first 6 words
        word_count = len(title.replace(" Dashboard", "").split())
        assert word_count <= 6

    def test_single_word_prompt(self) -> None:
        """Single-word prompts should produce a valid title."""
        title = _extract_title("revenue")
        assert title == "Revenue Dashboard"

    def test_empty_prompt(self) -> None:
        """Empty prompt should produce 'Dashboard' as the title."""
        title = _extract_title("")
        assert title == "Dashboard"

    def test_title_is_title_cased(self) -> None:
        """Output title should be Title Cased (capitalise each word)."""
        title = _extract_title("monthly active users breakdown")
        assert title[0].isupper()
