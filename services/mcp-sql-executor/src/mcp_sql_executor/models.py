"""
MCP SQL Executor — Pydantic models for requests, responses, and internal types.
Day 8: MCP tool I/O schemas enforced via Pydantic v2.

Protocols: MCP
SOLID: SRP (data shapes only)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class DatabaseTarget(str, Enum):
    POSTGRES = "postgres"
    CLICKHOUSE = "clickhouse"


class SQLDialect(str, Enum):
    POSTGRESQL = "postgresql"
    CLICKHOUSE = "clickhouse"


# ── Schema Discovery ─────────────────────────────────────────────────────────


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    description: str | None = None


class TableSchema(BaseModel):
    table_name: str
    schema_name: str
    columns: list[ColumnInfo]
    row_count: int | None = None
    description: str | None = None


class SchemaContext(BaseModel):
    database: DatabaseTarget
    tables: list[TableSchema]
    tenant_id: str


# ── NL-to-SQL ────────────────────────────────────────────────────────────────


class NLToSQLRequest(BaseModel):
    natural_language: str = Field(..., min_length=1, max_length=8_000)
    database: DatabaseTarget = DatabaseTarget.POSTGRES
    tenant_id: str
    schema_hint: list[str] | None = Field(
        default=None,
        description="Optional list of table names to narrow schema context",
    )


class NLToSQLResponse(BaseModel):
    sql: str
    dialect: SQLDialect
    confidence: float = Field(..., ge=0.0, le=1.0)
    tables_referenced: list[str]
    explanation: str
    langfuse_trace_id: str | None = None


# ── SQL Execution ────────────────────────────────────────────────────────────


class SQLExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=32_000)
    database: DatabaseTarget = DatabaseTarget.POSTGRES
    tenant_id: str
    parameters: dict[str, Any] | None = None
    max_rows: int = Field(default=1_000, ge=1, le=10_000)


class SQLExecuteResponse(BaseModel):
    rows: list[dict[str, Any]]
    row_count: int
    columns: list[str]
    execution_time_ms: float
    truncated: bool = False


# ── Number Verification ──────────────────────────────────────────────────────


class VerifyNumbersRequest(BaseModel):
    claim: str = Field(..., description="The numerical claim to verify, e.g. 'total revenue is $1.2M'")
    verification_sql: str = Field(..., description="SQL query that re-computes the claimed figure")
    database: DatabaseTarget = DatabaseTarget.POSTGRES
    tenant_id: str
    tolerance: float = Field(default=0.01, description="Acceptable relative tolerance (1% default)")


class VerifyNumbersResponse(BaseModel):
    verified: bool
    claimed_value: float | None
    actual_value: float | None
    discrepancy_pct: float | None
    verdict: str  # "VERIFIED", "MISMATCH", "INSUFFICIENT_DATA", "ERROR"
    details: str


# ── MCP Tool Results ─────────────────────────────────────────────────────────


class MCPToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
