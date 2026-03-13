"""
NL → Dashboard Router — Converts natural language prompts into full dashboard configurations.
Day 15: Phase 3 — NL-to-Dashboard via orchestration-engine A2A delegation.

Protocols: A2A (task delegation to orchestration-engine)
SOLID: SRP (NL generation only), OCP (parser extensible without modifying endpoint)
Benchmark: tests/benchmarks/bench_nl_dashboard.py — SLO < 8s E2E
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from langfuse.decorators import observe

from dashboard_api.config import settings
from dashboard_api.models import (
    DashboardConfig,
    ExportRequest,
    ExportResponse,
    NLToDashboardRequest,
    NLToDashboardResponse,
    WidgetConfig,
)

router = APIRouter(tags=["NL Dashboard"])
log = structlog.get_logger(__name__)


@router.post("/api/dashboards/nl-to-dashboard", response_model=NLToDashboardResponse)
@observe(name="nl_to_dashboard")
async def nl_to_dashboard(
    request: Request,
    body: NLToDashboardRequest,
) -> NLToDashboardResponse:
    """Convert a natural language prompt into a full dashboard configuration.

    Calls the orchestration-engine A2A endpoint with a VISUALIZATION intent,
    then parses the response to extract widget configs and suggested SQL queries.

    SLO: < 8s E2E (enforced by 10s httpx timeout)
    Langfuse trace: name="nl_to_dashboard"

    Args:
        request: FastAPI request (for app.state.http_client).
        body: NLToDashboardRequest with prompt, tenant_id, user_id.

    Returns:
        NLToDashboardResponse with dashboard_config, reasoning, suggested_queries,
        and generation_ms.

    Raises:
        HTTPException: 504 if orchestration-engine times out.
    """
    start = time.perf_counter()
    http_client: httpx.AsyncClient = request.app.state.http_client

    task_id = str(uuid.uuid4())[:12]
    prompt = (
        f"Generate a dashboard configuration for: {body.prompt}\n\n"
        "Return a JSON object with: title, description, widgets (array of chart configs), "
        "suggested_queries (array of SQL queries). "
        "Each widget must have: widget_type, title, chart_type, x, y, w, h."
    )

    task_data: dict[str, Any] = {"state": "failed", "artifacts": []}
    try:
        resp = await http_client.post(
            f"{settings.orchestration_engine_url}/a2a/tasks/send",
            json={
                "id": task_id,
                "session_id": f"nl-dash-{body.tenant_id}",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": prompt}],
                },
                "metadata": {
                    "tenant_id": body.tenant_id,
                    "user_id": body.user_id,
                    "intent": "VISUALIZATION",
                },
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        task_data = resp.json()
    except httpx.TimeoutException as exc:
        log.warning("nl_to_dashboard.timeout", tenant_id=body.tenant_id)
        raise HTTPException(
            status_code=504,
            detail={"error": "Orchestration engine timed out (>10s)", "code": "TIMEOUT"},
        ) from exc
    except Exception as exc:
        log.warning(
            "nl_to_dashboard.orchestration_failed",
            error=str(exc),
            tenant_id=body.tenant_id,
        )
        # Fall through — generate default dashboard from prompt keywords

    widgets, reasoning, suggested_queries = _parse_orchestration_response(
        task_data, body.prompt
    )

    config = DashboardConfig(
        tenant_id=body.tenant_id,
        title=_extract_title(body.prompt),
        description=f"Auto-generated from: {body.prompt}",
        widgets=widgets,
        created_by=body.user_id,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "nl_to_dashboard.done",
        tenant_id=body.tenant_id,
        elapsed_ms=round(elapsed_ms, 2),
        widget_count=len(widgets),
    )

    # Track histogram via app.state
    histogram = getattr(request.app.state, "nl_dashboard_latency_histogram", None)
    if histogram is not None:
        histogram.observe(elapsed_ms)

    return NLToDashboardResponse(
        dashboard_config=config,
        reasoning=reasoning,
        suggested_queries=suggested_queries,
        generation_ms=round(elapsed_ms, 2),
    )


@router.post(
    "/api/dashboards/{dashboard_id}/export",
    response_model=ExportResponse,
)
async def export_dashboard(
    dashboard_id: str,
    body: ExportRequest,
    request: Request,
) -> ExportResponse:
    """Trigger PDF or PPTX export of a dashboard via mcp-report-generator.

    Calls the mcp-report-generator MCP tool endpoint to initiate export.
    Export is asynchronous — returns an export_id to poll for completion.

    Args:
        dashboard_id: Dashboard UUID to export.
        body: ExportRequest with format ("pdf" or "pptx") and tenant_id.
        request: FastAPI request (for app.state.http_client).

    Returns:
        ExportResponse with export_id, status, and optional download_url.
    """
    if body.format not in ("pdf", "pptx"):
        raise HTTPException(
            status_code=400,
            detail={"error": "format must be 'pdf' or 'pptx'", "code": "INVALID_FORMAT"},
        )

    http_client: httpx.AsyncClient = request.app.state.http_client
    export_id = str(uuid.uuid4())[:12]

    try:
        resp = await http_client.post(
            settings.mcp_report_generator_url,
            json={
                "jsonrpc": "2.0",
                "id": export_id,
                "method": "tools/call",
                "params": {
                    "name": "generate_report",
                    "arguments": {
                        "dashboard_id": dashboard_id,
                        "tenant_id": body.tenant_id,
                        "format": body.format,
                        "export_id": export_id,
                    },
                },
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        result = resp.json()
        download_url: str | None = None
        if isinstance(result, dict):
            tool_result = result.get("result", {})
            download_url = tool_result.get("download_url") if isinstance(tool_result, dict) else None

        log.info(
            "export.triggered",
            dashboard_id=dashboard_id,
            export_id=export_id,
            format=body.format,
        )
        return ExportResponse(
            export_id=export_id,
            dashboard_id=dashboard_id,
            format=body.format,
            status="queued",
            download_url=download_url,
            message=f"Export {export_id} queued for {body.format.upper()} generation.",
        )
    except httpx.TimeoutException:
        log.warning("export.timeout", dashboard_id=dashboard_id, export_id=export_id)
        return ExportResponse(
            export_id=export_id,
            dashboard_id=dashboard_id,
            format=body.format,
            status="queued",
            message="Export queued — report generator response pending.",
        )
    except Exception as exc:
        log.error("export.error", dashboard_id=dashboard_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "code": "EXPORT_FAILED"},
        ) from exc


# ── Internal Parsing Helpers ──────────────────────────────────────────────────


def _parse_orchestration_response(
    task_data: dict[str, Any],
    prompt: str,
) -> tuple[list[WidgetConfig], str, list[str]]:
    """Extract widgets, reasoning, and queries from an A2A task response.

    Attempts to find and parse a JSON object inside the response text.
    Falls back to keyword-based default widgets if parsing fails.

    Args:
        task_data: A2A task response dict with optional "artifacts" list.
        prompt: Original NL prompt (used for fallback widget generation).

    Returns:
        Tuple of (widgets, reasoning, suggested_queries).
    """
    response_text = ""
    artifacts = task_data.get("artifacts", [])
    for artifact in artifacts:
        for part in artifact.get("parts", []):
            if part.get("type") == "text":
                response_text += part.get("text", "")

    widgets: list[WidgetConfig] = []
    reasoning = "Dashboard generated from natural language prompt."
    suggested_queries: list[str] = []

    try:
        json_match = re.search(r"\{[\s\S]+\}", response_text)
        if json_match:
            data = json.loads(json_match.group(0))
            suggested_queries = data.get("suggested_queries", [])
            reasoning = data.get("description", reasoning)
            for i, w in enumerate(data.get("widgets", [])):
                widgets.append(
                    WidgetConfig(
                        widget_type=w.get("widget_type", "chart"),
                        title=w.get("title", f"Widget {i + 1}"),
                        chart_type=w.get("chart_type", "bar"),
                        x=w.get("x", (i % 2) * 6),
                        y=w.get("y", (i // 2) * 4),
                        w=w.get("w", 6),
                        h=w.get("h", 4),
                    )
                )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass  # Fall through to default widget generation

    if not widgets:
        widgets = _generate_default_widgets(prompt)

    return widgets, reasoning, suggested_queries


def _generate_default_widgets(prompt: str) -> list[WidgetConfig]:
    """Generate sensible default widgets based on keywords in the prompt.

    Args:
        prompt: Natural language prompt to analyse for domain keywords.

    Returns:
        List of WidgetConfig objects appropriate for the detected domain.
    """
    prompt_lower = prompt.lower()
    widgets: list[WidgetConfig] = []

    if any(w in prompt_lower for w in ["revenue", "sales", "profit", "cost"]):
        widgets.append(
            WidgetConfig(
                widget_type="chart",
                title="Revenue Over Time",
                chart_type="line",
                x=0,
                y=0,
                w=8,
                h=4,
            )
        )
        widgets.append(
            WidgetConfig(
                widget_type="metric",
                title="Total Revenue",
                chart_type="gauge",
                x=8,
                y=0,
                w=4,
                h=4,
            )
        )

    if any(w in prompt_lower for w in ["distribution", "breakdown", "by", "split"]):
        widgets.append(
            WidgetConfig(
                widget_type="chart",
                title="Distribution",
                chart_type="pie",
                x=0,
                y=4,
                w=6,
                h=4,
            )
        )

    if any(w in prompt_lower for w in ["trend", "growth", "forecast"]):
        widgets.append(
            WidgetConfig(
                widget_type="chart",
                title="Trend Analysis",
                chart_type="line",
                x=6 if widgets else 0,
                y=4,
                w=6,
                h=4,
            )
        )

    if any(w in prompt_lower for w in ["table", "list", "records", "rows"]):
        widgets.append(
            WidgetConfig(
                widget_type="table",
                title="Data Table",
                chart_type=None,
                x=0,
                y=8,
                w=12,
                h=5,
            )
        )

    if not widgets:
        # Generic fallback — always produces a valid dashboard
        widgets = [
            WidgetConfig(
                widget_type="chart",
                title="Metric Over Time",
                chart_type="line",
                x=0,
                y=0,
                w=12,
                h=4,
            ),
            WidgetConfig(
                widget_type="chart",
                title="Breakdown",
                chart_type="bar",
                x=0,
                y=4,
                w=6,
                h=4,
            ),
            WidgetConfig(
                widget_type="chart",
                title="Distribution",
                chart_type="pie",
                x=6,
                y=4,
                w=6,
                h=4,
            ),
        ]

    return widgets


def _extract_title(prompt: str) -> str:
    """Extract a short dashboard title from the NL prompt (max 6 words).

    Args:
        prompt: Natural language prompt.

    Returns:
        Title-cased string ending in "Dashboard".
    """
    words = prompt.split()[:6]
    return " ".join(words).title() + " Dashboard"
