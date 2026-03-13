"""
dbt Model Executor — runs dbt models via subprocess, captures output.
Day 11: Phase 2 — dbt-core CLI wrapper with async subprocess execution.

Protocols: None
SOLID: SRP (execution only), OCP (IModelExecutor ABC), DIP (injected into MCP tools)
Benchmark: tests/benchmarks/bench_dbt.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import structlog

from mcp_dbt_runner.config import settings
from mcp_dbt_runner.models import RunModelResponse

log = structlog.get_logger(__name__)


class IModelExecutor(ABC):
    """Abstract interface for dbt model execution.

    SOLID OCP: new executor implementations add files, never modify this ABC.
    """

    @abstractmethod
    async def run(
        self,
        model_name: str,
        tenant_id: str,
        full_refresh: bool = False,
        vars: dict[str, Any] | None = None,
        select: str | None = None,
    ) -> RunModelResponse:
        """Execute a dbt model and return a structured result.

        Args:
            model_name: Target dbt model name.
            tenant_id: Tenant identifier used to isolate the output schema.
            full_refresh: Whether to run with --full-refresh.
            vars: Optional dbt variable overrides passed via --vars.
            select: Optional dbt --select selector expression.

        Returns:
            RunModelResponse with status, rows_affected, compiled_sql, and logs.
        """
        ...


class DBTExecutor(IModelExecutor):
    """Executes dbt models via dbt-core CLI as an async subprocess.

    Tenant isolation is achieved by injecting DBT_TARGET_SCHEMA as an
    environment variable so the dbt profile resolves to a per-tenant schema
    (e.g., ``dbt_tenant_abc``).  A 300-second hard timeout prevents runaway
    queries from blocking the event loop.
    """

    async def run(
        self,
        model_name: str,
        tenant_id: str,
        full_refresh: bool = False,
        vars: dict[str, Any] | None = None,
        select: str | None = None,
    ) -> RunModelResponse:
        """Execute a dbt model and capture structured output.

        Args:
            model_name: Target dbt model name (e.g., ``stg_orders``).
            tenant_id: Tenant ID injected as ``DBT_TARGET_SCHEMA=dbt_{tenant_id}``.
            full_refresh: Pass ``--full-refresh`` to dbt CLI.
            vars: Python dict serialised to JSON for ``--vars``.
            select: dbt node selector expression (defaults to ``model_name``).

        Returns:
            RunModelResponse with run_id, status, rows_affected, compiled_sql,
            execution_ms, and the last 20 log lines.
        """
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        cmd: list[str] = [
            "dbt",
            "run",
            "--project-dir",
            settings.dbt_project_dir,
            "--profiles-dir",
            settings.dbt_profiles_dir,
            "--target",
            settings.dbt_target,
            "--select",
            select or model_name,
            "--no-write-json",
        ]
        if full_refresh:
            cmd.append("--full-refresh")
        if vars:
            cmd.extend(["--vars", json.dumps(vars)])

        log.info("dbt.run.start", model=model_name, run_id=run_id, tenant_id=tenant_id)

        env = {**os.environ, "DBT_TARGET_SCHEMA": f"dbt_{tenant_id}"}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            output = stdout.decode("utf-8", errors="replace")
            lines = output.splitlines()
            elapsed = (time.perf_counter() - start) * 1000

            status = "success" if proc.returncode == 0 else "error"
            rows_affected = _parse_rows_affected(output)
            compiled_sql = _parse_compiled_sql(output)

            log.info(
                "dbt.run.done",
                model=model_name,
                run_id=run_id,
                status=status,
                elapsed_ms=round(elapsed, 2),
                rows_affected=rows_affected,
            )

            return RunModelResponse(
                run_id=run_id,
                model_name=model_name,
                status=status,
                rows_affected=rows_affected,
                execution_ms=round(elapsed, 2),
                compiled_sql=compiled_sql[:500],
                logs=lines[-20:],
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            log.error("dbt.run.timeout", model=model_name, run_id=run_id)
            return RunModelResponse(
                run_id=run_id,
                model_name=model_name,
                status="error",
                rows_affected=0,
                execution_ms=round(elapsed, 2),
                compiled_sql="",
                logs=["ERROR: dbt run timed out after 300s"],
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            log.error("dbt.run.error", model=model_name, run_id=run_id, error=str(exc))
            return RunModelResponse(
                run_id=run_id,
                model_name=model_name,
                status="error",
                rows_affected=0,
                execution_ms=round(elapsed, 2),
                compiled_sql="",
                logs=[f"ERROR: {exc}"],
            )


def _parse_rows_affected(output: str) -> int:
    """Extract the rows-affected count from dbt CLI output.

    Handles two common dbt output formats:
    - ``123 rows affected``
    - ``Inserted 50 records`` (some adapters)

    Args:
        output: Full stdout string from dbt CLI.

    Returns:
        Integer row count, or 0 when not found.
    """
    match = re.search(r"(\d+)\s+rows?\s+affected", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"Inserted\s+(\d+)\s+records?", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # dbt incremental: "1 of 1 START ... [INSERT 42 in 0.45s]"
    match = re.search(r"\[INSERT\s+(\d+)\s+in", output)
    if match:
        return int(match.group(1))
    return 0


def _parse_compiled_sql(output: str) -> str:
    """Extract the last compiled SELECT statement from dbt CLI output.

    dbt prints the compiled SQL to stdout when running in debug mode or
    via certain adapters.  This function extracts the last SELECT block
    found in the output for display purposes.

    Args:
        output: Full stdout string from dbt CLI.

    Returns:
        Compiled SQL string (may be empty if not present in output).
    """
    matches = re.findall(r"(SELECT[\s\S]+?)(?:\n\n|\Z)", output, re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    return ""
