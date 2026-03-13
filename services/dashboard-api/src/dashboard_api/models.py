"""
Dashboard API Models — Pydantic request/response models for dashboard operations.
Day 15: Phase 3 — Visualization & Dashboard data models.

Protocols: None
SOLID: SRP (models only), LSP (all subclasses honour BaseModel contract)
Benchmark: N/A
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class WidgetConfig(BaseModel):
    """Single widget in a dashboard grid.

    Matches react-grid-layout item format for the frontend drag-and-drop builder.
    """

    widget_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    widget_type: str  # "chart", "metric", "table", "text", "map"
    title: str
    # Grid position (react-grid-layout format)
    x: int = 0
    y: int = 0
    w: int = 6  # columns (out of 12)
    h: int = 4  # row units
    # Widget data config
    chart_type: str | None = None  # bar/line/pie/etc for chart widgets
    data_source: dict[str, Any] = Field(default_factory=dict)  # query config
    chart_config: dict[str, Any] = Field(default_factory=dict)  # ECharts option override
    refresh_interval_s: int = 0  # 0 = no auto-refresh


class DashboardConfig(BaseModel):
    """Full dashboard layout and widget definitions.

    Persisted as JSONB in PostgreSQL datamind_core.dashboards table.
    """

    dashboard_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    title: str
    description: str = ""
    widgets: list[WidgetConfig] = Field(default_factory=list)
    theme: str = "dark"
    cols: int = 12
    row_height: int = 80
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
    tags: list[str] = Field(default_factory=list)


class CreateDashboardRequest(BaseModel):
    """Request body for POST /api/dashboards."""

    tenant_id: str
    title: str
    description: str = ""
    widgets: list[WidgetConfig] = Field(default_factory=list)
    theme: str = "dark"
    tags: list[str] = Field(default_factory=list)


class UpdateDashboardRequest(BaseModel):
    """Request body for PUT /api/dashboards/{dashboard_id}.

    All fields are optional — only provided fields are updated (PATCH semantics).
    """

    title: str | None = None
    description: str | None = None
    widgets: list[WidgetConfig] | None = None
    theme: str | None = None
    tags: list[str] | None = None


class NLToDashboardRequest(BaseModel):
    """Request body for POST /api/dashboards/nl-to-dashboard."""

    prompt: str
    tenant_id: str
    user_id: str = "system"
    context: dict[str, Any] = Field(default_factory=dict)


class NLToDashboardResponse(BaseModel):
    """Response for NL → Dashboard generation.

    SLO: generation_ms < 8000ms E2E.
    """

    dashboard_config: DashboardConfig
    reasoning: str
    suggested_queries: list[str]
    generation_ms: float


class ExportRequest(BaseModel):
    """Request body for POST /api/dashboards/{dashboard_id}/export."""

    format: str = "pdf"  # "pdf" or "pptx"
    tenant_id: str


class ExportResponse(BaseModel):
    """Response for dashboard export trigger."""

    export_id: str
    dashboard_id: str
    format: str
    status: str  # "queued", "processing", "completed", "failed"
    download_url: str | None = None
    message: str = ""


class WebSocketMessage(BaseModel):
    """Message envelope for WebSocket real-time dashboard stream."""

    type: str  # "snapshot", "update", "event", "heartbeat", "error"
    dashboard_id: str
    data: Any = None
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
