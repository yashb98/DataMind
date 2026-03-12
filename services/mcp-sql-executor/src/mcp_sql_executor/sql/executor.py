"""
MCP SQL Executor — SQL execution against PostgreSQL and ClickHouse.
Day 8: Async execution with tenant isolation, row limits, and timeout enforcement.

Protocols: None (internal component)
SOLID: SRP (execution only), OCP (new DB = new method, ISQLExecutor ABC)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import asyncpg
import sqlparse
import structlog
from clickhouse_driver import Client as ClickHouseClient

from mcp_sql_executor.config import Settings
from mcp_sql_executor.models import DatabaseTarget, SQLExecuteResponse

log = structlog.get_logger(__name__)

# ── ISQLExecutor ABC (OCP/DIP) ────────────────────────────────────────────────


class ISQLExecutor(ABC):
    """Interface for database-specific SQL execution."""

    @abstractmethod
    async def execute(
        self,
        sql: str,
        tenant_id: str,
        parameters: dict[str, Any] | None,
        max_rows: int,
        timeout_s: int,
    ) -> SQLExecuteResponse:
        """Execute SQL and return structured results."""
        ...

    @abstractmethod
    async def get_schema(
        self, tenant_id: str, table_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Return table schema information."""
        ...


# ── PostgreSQL Executor ───────────────────────────────────────────────────────


class PostgreSQLExecutor(ISQLExecutor):
    """Executes SQL against PostgreSQL with asyncpg and tenant row-level isolation."""

    def __init__(self, settings: Settings, pool: asyncpg.Pool) -> None:
        self._settings = settings
        self._pool = pool

    async def execute(
        self,
        sql: str,
        tenant_id: str,
        parameters: dict[str, Any] | None,
        max_rows: int,
        timeout_s: int,
    ) -> SQLExecuteResponse:
        """Execute SQL with tenant context, limits, and timeout.

        Args:
            sql: SQL query to execute. Must be read-only (SELECT).
            tenant_id: Tenant identifier for isolation enforcement.
            parameters: Optional named parameters for parameterised queries.
            max_rows: Maximum rows to return.
            timeout_s: Query timeout in seconds.

        Returns:
            Structured result set with metadata.

        Raises:
            ValueError: If SQL contains write operations.
            asyncpg.PostgresError: On database errors.
        """
        _assert_read_only(sql)
        # Inject LIMIT to enforce max_rows
        limited_sql = _inject_limit(sql, max_rows + 1)

        start = time.perf_counter()
        async with self._pool.acquire() as conn:
            # Set tenant context variable for row-level security
            await conn.execute(f"SET app.current_tenant = '{tenant_id}'")
            try:
                rows = await conn.fetch(limited_sql, timeout=timeout_s)
            except asyncpg.PostgresError as exc:
                log.error("postgres.execute.error", tenant_id=tenant_id, error=str(exc))
                raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        columns = list(rows[0].keys()) if rows else []
        result_rows = [dict(r) for r in rows]

        log.info(
            "postgres.execute.ok",
            tenant_id=tenant_id,
            row_count=len(result_rows),
            elapsed_ms=round(elapsed_ms, 2),
        )
        return SQLExecuteResponse(
            rows=result_rows,
            row_count=len(result_rows),
            columns=columns,
            execution_time_ms=round(elapsed_ms, 2),
            truncated=truncated,
        )

    async def get_schema(
        self, tenant_id: str, table_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve table schemas from information_schema.

        Args:
            tenant_id: Tenant identifier.
            table_names: Optional filter on specific tables.

        Returns:
            List of table dicts with columns metadata.
        """
        schema_filter = ""
        if table_names:
            quoted = ", ".join(f"'{t}'" for t in table_names)
            schema_filter = f"AND c.table_name IN ({quoted})"

        query = f"""
            SELECT
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                pgd.description AS column_comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_statio_all_tables st
                ON st.schemaname = c.table_schema AND st.relname = c.table_name
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
            WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
            {schema_filter}
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """  # noqa: S608 (read-only schema query)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)

        # Group by table
        tables: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = f"{row['table_schema']}.{row['table_name']}"
            if key not in tables:
                tables[key] = {
                    "schema": row["table_schema"],
                    "table": row["table_name"],
                    "columns": [],
                }
            tables[key]["columns"].append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "comment": row["column_comment"],
                }
            )

        return list(tables.values())


# ── ClickHouse Executor ───────────────────────────────────────────────────────


class ClickHouseExecutor(ISQLExecutor):
    """Executes SQL against ClickHouse for analytics queries."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = ClickHouseClient(
            host=settings.clickhouse_host,
            port=9000,  # Native TCP port
            database=settings.clickhouse_db,
            user=settings.clickhouse_user,
            password=settings.clickhouse_password,
            connect_timeout=settings.query_timeout_s,
            send_receive_timeout=settings.query_timeout_s,
        )

    async def execute(
        self,
        sql: str,
        tenant_id: str,
        parameters: dict[str, Any] | None,
        max_rows: int,
        timeout_s: int,
    ) -> SQLExecuteResponse:
        """Execute SQL against ClickHouse.

        Note: clickhouse-driver is synchronous; runs in thread pool.
        """
        import asyncio

        _assert_read_only(sql)
        limited_sql = _inject_limit(sql, max_rows + 1)

        loop = asyncio.get_event_loop()
        start = time.perf_counter()

        def _sync_execute() -> tuple[list[Any], list[Any]]:
            result = self._client.execute(limited_sql, with_column_types=True)
            return result  # type: ignore[return-value]

        rows_raw, col_types = await loop.run_in_executor(None, _sync_execute)
        elapsed_ms = (time.perf_counter() - start) * 1000

        columns = [ct[0] for ct in col_types]
        truncated = len(rows_raw) > max_rows
        rows_raw = rows_raw[:max_rows]
        result_rows = [dict(zip(columns, row)) for row in rows_raw]

        log.info(
            "clickhouse.execute.ok",
            tenant_id=tenant_id,
            row_count=len(result_rows),
            elapsed_ms=round(elapsed_ms, 2),
        )
        return SQLExecuteResponse(
            rows=result_rows,
            row_count=len(result_rows),
            columns=columns,
            execution_time_ms=round(elapsed_ms, 2),
            truncated=truncated,
        )

    async def get_schema(
        self, tenant_id: str, table_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve ClickHouse table schemas."""
        import asyncio

        table_filter = ""
        if table_names:
            quoted = ", ".join(f"'{t}'" for t in table_names)
            table_filter = f"AND name IN ({quoted})"

        query = f"""
            SELECT
                database,
                table,
                name,
                type,
                comment
            FROM system.columns
            WHERE database = '{self._settings.clickhouse_db}'
            {table_filter}
            ORDER BY table, position
        """  # noqa: S608

        def _sync_schema() -> tuple[list[Any], list[Any]]:
            return self._client.execute(query, with_column_types=True)  # type: ignore[return-value]

        loop = asyncio.get_event_loop()
        rows_raw, _ = await loop.run_in_executor(None, _sync_schema)

        tables: dict[str, dict[str, Any]] = {}
        for row in rows_raw:
            db, table, col_name, col_type, comment = row
            key = f"{db}.{table}"
            if key not in tables:
                tables[key] = {"schema": db, "table": table, "columns": []}
            tables[key]["columns"].append(
                {"name": col_name, "type": col_type, "nullable": True, "comment": comment}
            )

        return list(tables.values())


# ── Routing Facade ────────────────────────────────────────────────────────────


class SQLExecutorRouter:
    """Routes SQL execution to the correct database executor (OCP/DIP).

    New databases: add an ISQLExecutor implementation, register here.
    Zero modification to existing executors.
    """

    def __init__(
        self,
        postgres: PostgreSQLExecutor,
        clickhouse: ClickHouseExecutor,
        settings: Settings,
    ) -> None:
        self._executors: dict[DatabaseTarget, ISQLExecutor] = {
            DatabaseTarget.POSTGRES: postgres,
            DatabaseTarget.CLICKHOUSE: clickhouse,
        }
        self._settings = settings

    def get_executor(self, target: DatabaseTarget) -> ISQLExecutor:
        executor = self._executors.get(target)
        if executor is None:
            raise ValueError(f"No executor registered for target: {target}")
        return executor


# ── Helpers ───────────────────────────────────────────────────────────────────


def _assert_read_only(sql: str) -> None:
    """Reject any non-SELECT SQL to prevent write operations via MCP.

    Args:
        sql: SQL string to validate.

    Raises:
        ValueError: If SQL contains write operations.
    """
    parsed = sqlparse.parse(sql.strip())
    for statement in parsed:
        stmt_type = statement.get_type()
        if stmt_type and stmt_type.upper() not in ("SELECT", "UNKNOWN", None):
            raise ValueError(
                f"Only SELECT statements are allowed via MCP SQL Executor. Got: {stmt_type}"
            )
    # Extra guard: check for DML keywords
    upper = sql.upper()
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT")
    for kw in forbidden:
        if kw in upper:
            raise ValueError(f"Forbidden keyword '{kw}' detected in SQL query.")


def _inject_limit(sql: str, limit: int) -> str:
    """Inject LIMIT clause if not already present.

    Args:
        sql: Original SQL query.
        limit: Maximum row limit to enforce.

    Returns:
        SQL with LIMIT clause.
    """
    stripped = sql.strip().rstrip(";")
    if "LIMIT" not in stripped.upper():
        return f"{stripped} LIMIT {limit}"
    return stripped
