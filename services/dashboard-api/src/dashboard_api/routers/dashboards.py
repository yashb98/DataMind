"""
Dashboard CRUD Router — REST endpoints for dashboard lifecycle management.
Day 15: Phase 3 — Full CRUD using asyncpg against datamind_core.dashboards.

Protocols: None
SOLID: SRP (CRUD only), DIP (asyncpg.Pool injected via app.state)
Benchmark: N/A
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Request, status

from dashboard_api.models import (
    CreateDashboardRequest,
    DashboardConfig,
    UpdateDashboardRequest,
    WidgetConfig,
)

router = APIRouter(tags=["Dashboards"])
log = structlog.get_logger(__name__)

# ── SQL DDL (executed at startup) ─────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS datamind_core.dashboards (
    dashboard_id TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT DEFAULT '',
    config       JSONB NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    created_by   TEXT DEFAULT 'system',
    tags         TEXT[] DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_dashboards_tenant
    ON datamind_core.dashboards(tenant_id);
"""


# ── Dependency ────────────────────────────────────────────────────────────────


async def get_db_pool(request: Request) -> asyncpg.Pool:
    """Retrieve shared asyncpg pool from app.state.

    Args:
        request: FastAPI request with app.state.db_pool.

    Returns:
        asyncpg.Pool instance.

    Raises:
        HTTPException: 503 if pool is not initialised.
    """
    pool: asyncpg.Pool | None = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Database pool not initialised", "code": "DB_POOL_UNAVAILABLE"},
        )
    return pool


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_config(row: asyncpg.Record) -> DashboardConfig:
    """Convert a asyncpg Record to DashboardConfig.

    Args:
        row: Database row with columns matching datamind_core.dashboards.

    Returns:
        DashboardConfig populated from row data.
    """
    config_data: dict[str, Any] = row["config"] if isinstance(row["config"], dict) else {}
    widgets = [WidgetConfig(**w) for w in config_data.get("widgets", [])]
    return DashboardConfig(
        dashboard_id=row["dashboard_id"],
        tenant_id=row["tenant_id"],
        title=row["title"],
        description=row["description"] or "",
        widgets=widgets,
        theme=config_data.get("theme", "dark"),
        cols=config_data.get("cols", 12),
        row_height=config_data.get("row_height", 80),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row["created_by"] or "system",
        tags=list(row["tags"] or []),
    )


def _config_to_jsonb(cfg: DashboardConfig) -> str:
    """Serialise the mutable parts of DashboardConfig to JSONB string.

    Args:
        cfg: DashboardConfig to serialise.

    Returns:
        JSON string suitable for asyncpg JSONB column.
    """
    return json.dumps(
        {
            "widgets": [w.model_dump() for w in cfg.widgets],
            "theme": cfg.theme,
            "cols": cfg.cols,
            "row_height": cfg.row_height,
        }
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/dashboards", response_model=list[DashboardConfig])
async def list_dashboards(
    tenant_id: str,
    request: Request,
) -> list[DashboardConfig]:
    """List all dashboards belonging to a tenant, ordered by last update.

    Args:
        tenant_id: Tenant identifier (query parameter).
        request: FastAPI request (for app.state.db_pool access).

    Returns:
        List of DashboardConfig objects ordered by updated_at DESC.
    """
    pool = await get_db_pool(request)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT dashboard_id, tenant_id, title, description,
                       config, created_at, updated_at, created_by, tags
                FROM datamind_core.dashboards
                WHERE tenant_id = $1
                ORDER BY updated_at DESC
                """,
                tenant_id,
            )
        result = [_row_to_config(row) for row in rows]
        log.info("dashboards.list", tenant_id=tenant_id, count=len(result))
        return result
    except Exception as exc:
        log.error("dashboards.list.error", error=str(exc), tenant_id=tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "LIST_FAILED"},
        ) from exc


@router.post(
    "/api/dashboards",
    response_model=DashboardConfig,
    status_code=status.HTTP_201_CREATED,
)
async def create_dashboard(
    body: CreateDashboardRequest,
    request: Request,
) -> DashboardConfig:
    """Create a new dashboard and persist it to PostgreSQL.

    Args:
        body: CreateDashboardRequest with tenant_id, title, widgets, etc.
        request: FastAPI request (for app.state.db_pool and metrics).

    Returns:
        Created DashboardConfig with generated dashboard_id.
    """
    pool = await get_db_pool(request)
    now = datetime.now(timezone.utc)
    cfg = DashboardConfig(
        tenant_id=body.tenant_id,
        title=body.title,
        description=body.description,
        widgets=body.widgets,
        theme=body.theme,
        tags=body.tags,
        created_at=now,
        updated_at=now,
    )
    config_json = _config_to_jsonb(cfg)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO datamind_core.dashboards
                    (dashboard_id, tenant_id, title, description,
                     config, created_at, updated_at, created_by, tags)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9)
                """,
                cfg.dashboard_id,
                cfg.tenant_id,
                cfg.title,
                cfg.description,
                config_json,
                cfg.created_at,
                cfg.updated_at,
                cfg.created_by,
                cfg.tags,
            )
        # Increment Prometheus counter via app.state
        counter = getattr(request.app.state, "dashboard_creates_counter", None)
        if counter is not None:
            counter.labels(tenant_id=body.tenant_id).inc()
        log.info(
            "dashboards.created",
            dashboard_id=cfg.dashboard_id,
            tenant_id=body.tenant_id,
        )
        return cfg
    except Exception as exc:
        log.error("dashboards.create.error", error=str(exc), tenant_id=body.tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "CREATE_FAILED"},
        ) from exc


@router.get("/api/dashboards/{dashboard_id}", response_model=DashboardConfig)
async def get_dashboard(
    dashboard_id: str,
    tenant_id: str,
    request: Request,
) -> DashboardConfig:
    """Retrieve a single dashboard by ID, scoped to the tenant.

    Args:
        dashboard_id: Dashboard UUID.
        tenant_id: Tenant identifier (query parameter for isolation).
        request: FastAPI request.

    Returns:
        DashboardConfig for the requested dashboard.

    Raises:
        HTTPException: 404 if dashboard not found for this tenant.
    """
    pool = await get_db_pool(request)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT dashboard_id, tenant_id, title, description,
                       config, created_at, updated_at, created_by, tags
                FROM datamind_core.dashboards
                WHERE dashboard_id = $1 AND tenant_id = $2
                """,
                dashboard_id,
                tenant_id,
            )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Dashboard not found", "code": "NOT_FOUND"},
            )
        return _row_to_config(row)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("dashboards.get.error", error=str(exc), dashboard_id=dashboard_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "GET_FAILED"},
        ) from exc


@router.put("/api/dashboards/{dashboard_id}", response_model=DashboardConfig)
async def update_dashboard(
    dashboard_id: str,
    body: UpdateDashboardRequest,
    request: Request,
) -> DashboardConfig:
    """Update a dashboard's config (partial update — only provided fields are changed).

    Args:
        dashboard_id: Dashboard UUID.
        body: UpdateDashboardRequest with optional fields to update.
        request: FastAPI request.

    Returns:
        Updated DashboardConfig.

    Raises:
        HTTPException: 404 if dashboard not found.
    """
    pool = await get_db_pool(request)
    # Determine tenant_id from the body or re-fetch from DB first
    # We require tenant_id as a query param for isolation — retrieve current row first
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT dashboard_id, tenant_id, title, description,
                       config, created_at, updated_at, created_by, tags
                FROM datamind_core.dashboards
                WHERE dashboard_id = $1
                """,
                dashboard_id,
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "Dashboard not found", "code": "NOT_FOUND"},
                )
            current = _row_to_config(row)

            # Apply partial updates
            new_title = body.title if body.title is not None else current.title
            new_description = body.description if body.description is not None else current.description
            new_widgets = body.widgets if body.widgets is not None else current.widgets
            new_theme = body.theme if body.theme is not None else current.theme
            new_tags = body.tags if body.tags is not None else current.tags

            updated = current.model_copy(
                update={
                    "title": new_title,
                    "description": new_description,
                    "widgets": new_widgets,
                    "theme": new_theme,
                    "tags": new_tags,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            config_json = _config_to_jsonb(updated)

            await conn.execute(
                """
                UPDATE datamind_core.dashboards
                SET title       = $2,
                    description = $3,
                    config      = $4::jsonb,
                    updated_at  = NOW(),
                    tags        = $5
                WHERE dashboard_id = $1
                """,
                dashboard_id,
                new_title,
                new_description,
                config_json,
                new_tags,
            )

        log.info("dashboards.updated", dashboard_id=dashboard_id)
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        log.error("dashboards.update.error", error=str(exc), dashboard_id=dashboard_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "UPDATE_FAILED"},
        ) from exc


@router.delete("/api/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: str,
    tenant_id: str,
    request: Request,
) -> None:
    """Delete a dashboard by ID, scoped to the tenant.

    Args:
        dashboard_id: Dashboard UUID.
        tenant_id: Tenant identifier (query parameter for isolation).
        request: FastAPI request.

    Raises:
        HTTPException: 404 if dashboard not found for this tenant.
    """
    pool = await get_db_pool(request)
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM datamind_core.dashboards
                WHERE dashboard_id = $1 AND tenant_id = $2
                """,
                dashboard_id,
                tenant_id,
            )
        # asyncpg returns "DELETE N" — check N > 0
        deleted_count = int(result.split()[-1]) if result else 0
        if deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Dashboard not found", "code": "NOT_FOUND"},
            )
        log.info("dashboards.deleted", dashboard_id=dashboard_id, tenant_id=tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("dashboards.delete.error", error=str(exc), dashboard_id=dashboard_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": str(exc), "code": "DELETE_FAILED"},
        ) from exc
