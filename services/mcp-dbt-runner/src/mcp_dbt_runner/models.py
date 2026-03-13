"""
Models — Request/response Pydantic models for mcp-dbt-runner.
Day 11: Phase 2 — dbt Runner data models.

Protocols: None
SOLID: SRP (data shapes only)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunModelRequest(BaseModel):
    """Request to execute a dbt model."""

    model_name: str = Field(..., description="dbt model name (e.g., 'stg_orders')")
    tenant_id: str = Field(..., description="Tenant identifier for isolation")
    full_refresh: bool = Field(default=False, description="Run with --full-refresh flag")
    vars: dict[str, Any] = Field(default_factory=dict, description="dbt --vars override")
    select: str | None = Field(default=None, description="dbt --select selector expression")


class RunModelResponse(BaseModel):
    """Result of a dbt model execution."""

    run_id: str = Field(..., description="Unique run identifier (short UUID)")
    model_name: str = Field(..., description="Name of the executed dbt model")
    status: str = Field(..., description="Execution status: 'success', 'error', or 'skipped'")
    rows_affected: int = Field(..., description="Number of rows written/updated")
    execution_ms: float = Field(..., description="Total wall-clock time in milliseconds")
    compiled_sql: str = Field(..., description="Compiled SQL (first 500 chars)")
    logs: list[str] = Field(..., description="Last 20 lines of dbt stdout/stderr")


class GetLineageRequest(BaseModel):
    """Request to retrieve model lineage."""

    model_name: str = Field(..., description="dbt model to get lineage for")
    tenant_id: str = Field(..., description="Tenant identifier")
    direction: str = Field(
        default="both",
        description="Direction: 'upstream', 'downstream', or 'both'",
    )
    depth: int = Field(default=3, ge=1, le=10, description="Maximum hops to traverse")


class GetLineageResponse(BaseModel):
    """Lineage graph for a dbt model."""

    model_name: str = Field(..., description="Model name queried")
    upstream: list[str] = Field(default_factory=list, description="Upstream model dependencies")
    downstream: list[str] = Field(
        default_factory=list, description="Downstream models that depend on this one"
    )
    sources: list[str] = Field(default_factory=list, description="Raw source tables referenced")
    exposures: list[str] = Field(
        default_factory=list, description="Exposures (dashboards/reports) consuming this model"
    )
    dag_summary: str = Field(..., description="Human-readable DAG summary string")
