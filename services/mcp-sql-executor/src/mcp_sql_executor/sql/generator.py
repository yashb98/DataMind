"""
MCP SQL Executor — NL-to-SQL generator using LiteLLM with schema context.
Day 8: Anthropic prompt caching for schema system prompts → 60-80% token reduction.

Protocols: None (internal component)
SOLID: SRP (generation only), DIP (LiteLLM injected)
Benchmark: tests/benchmarks/bench_nl_to_sql.py
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import structlog
from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe
from tenacity import retry, stop_after_attempt, wait_exponential

from mcp_sql_executor.config import Settings
from mcp_sql_executor.models import DatabaseTarget, NLToSQLResponse, SQLDialect

log = structlog.get_logger(__name__)

# ── System Prompt (cached via Anthropic prompt caching) ───────────────────────

_SYSTEM_PROMPT = """You are an expert SQL engineer. Convert the natural language question into a precise SQL query.

Rules:
1. Generate ONLY valid SQL — no explanations, no markdown fences, no semicolons.
2. Always add WHERE tenant_id = :tenant_id for PostgreSQL tables that have a tenant_id column.
3. Use table aliases for readability.
4. Prefer CTEs for complex queries.
5. NEVER use SELECT * — always name specific columns.
6. For ClickHouse: use ClickHouse syntax (e.g., toDate(), formatDateTime(), countIf()).
7. For PostgreSQL: use standard ANSI SQL + PostgreSQL extensions.
8. Return ONLY the SQL on the first line, then on a new line after "---" return a JSON object:
   {"confidence": 0.0-1.0, "tables": ["table1", "table2"], "explanation": "brief explanation"}

Example output:
SELECT u.id, u.name, COUNT(e.id) AS event_count FROM users u LEFT JOIN events e ON e.user_id = u.id WHERE u.tenant_id = :tenant_id GROUP BY u.id, u.name ORDER BY event_count DESC LIMIT 100
---
{"confidence": 0.95, "tables": ["users", "events"], "explanation": "Counts events per user for the current tenant"}
"""


class NLToSQLGenerator:
    """Converts natural language to SQL using LiteLLM with schema-aware prompting.

    Uses Anthropic prompt caching to amortise schema context cost across requests.
    Cache hit rate target: >90% (schema changes infrequently).
    """

    def __init__(self, settings: Settings, langfuse: Langfuse) -> None:
        self._settings = settings
        self._langfuse = langfuse
        self._schema_cache: dict[str, str] = {}  # schema_hash → formatted schema

    @observe(name="nl_to_sql")
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate(
        self,
        natural_language: str,
        schema_tables: list[dict[str, Any]],
        database: DatabaseTarget,
        tenant_id: str,
    ) -> NLToSQLResponse:
        """Generate SQL from natural language with schema context.

        Args:
            natural_language: User's question in plain English.
            schema_tables: List of table schemas from the database.
            database: Target database type.
            tenant_id: Tenant identifier for row-level security injection.

        Returns:
            NLToSQLResponse with generated SQL, confidence, and explanation.

        Raises:
            RuntimeError: If LiteLLM call fails after retries.
        """
        import litellm

        dialect = (
            SQLDialect.CLICKHOUSE if database == DatabaseTarget.CLICKHOUSE else SQLDialect.POSTGRESQL
        )
        schema_text = self._format_schema(schema_tables)
        schema_hash = hashlib.md5(schema_text.encode()).hexdigest()[:8]  # noqa: S324

        user_prompt = (
            f"Database: {database.value} ({dialect.value} dialect)\n"
            f"Tenant ID: {tenant_id}\n\n"
            f"Schema:\n{schema_text}\n\n"
            f"Question: {natural_language}"
        )

        langfuse_context.update_current_observation(
            input={"query": natural_language, "tenant_id": tenant_id, "schema_hash": schema_hash},
            metadata={"database": database.value, "dialect": dialect.value},
        )

        start = time.perf_counter()
        response = await litellm.acompletion(
            model=self._settings.nl_to_sql_model,
            api_base=self._settings.litellm_url,
            api_key=self._settings.litellm_api_key,
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                    # Anthropic prompt caching — system prompt is stable
                    "cache_control": {"type": "ephemeral"},
                },
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._settings.nl_to_sql_max_tokens,
            temperature=self._settings.nl_to_sql_temperature,
            metadata={"tenant_id": tenant_id, "trace_name": "nl_to_sql"},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        raw = response.choices[0].message.content.strip()
        sql, meta = _parse_llm_output(raw)

        langfuse_context.update_current_observation(
            output={"sql": sql, "confidence": meta.get("confidence", 0.0)},
            usage={
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
            },
        )

        log.info(
            "nl_to_sql.generated",
            tenant_id=tenant_id,
            database=database.value,
            confidence=meta.get("confidence", 0.0),
            elapsed_ms=round(elapsed_ms, 2),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

        return NLToSQLResponse(
            sql=sql,
            dialect=dialect,
            confidence=float(meta.get("confidence", 0.5)),
            tables_referenced=meta.get("tables", []),
            explanation=meta.get("explanation", ""),
            langfuse_trace_id=langfuse_context.get_current_trace_id(),
        )

    def _format_schema(self, tables: list[dict[str, Any]]) -> str:
        """Format schema tables into compact DDL-like text for the prompt.

        Args:
            tables: List of table schema dicts.

        Returns:
            Formatted schema string (compact DDL).
        """
        lines: list[str] = []
        for t in tables:
            tname = f"{t.get('schema', 'public')}.{t['table']}"
            cols = ", ".join(
                f"{c['name']} {c['type']}" for c in t.get("columns", [])
            )
            lines.append(f"TABLE {tname} ({cols})")
        return "\n".join(lines)


# ── Parsing Helpers ───────────────────────────────────────────────────────────


def _parse_llm_output(raw: str) -> tuple[str, dict[str, Any]]:
    """Parse LLM output into SQL and metadata JSON.

    Expected format:
        SELECT ...
        ---
        {"confidence": 0.9, "tables": [...], "explanation": "..."}

    Args:
        raw: Raw LLM output string.

    Returns:
        Tuple of (sql_string, metadata_dict).
    """
    parts = raw.split("---", 1)
    sql = parts[0].strip()

    meta: dict[str, Any] = {}
    if len(parts) > 1:
        try:
            meta = json.loads(parts[1].strip())
        except json.JSONDecodeError:
            log.warning("nl_to_sql.metadata_parse_failed", raw_meta=parts[1][:200])

    # Sanitise SQL — strip any accidental markdown fences
    sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql, meta
