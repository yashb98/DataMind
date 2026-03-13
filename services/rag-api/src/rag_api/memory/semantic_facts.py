"""
RAG API — pgvector Semantic Facts Store.
Day 22: Phase 5 — Long-lived factual assertions stored with vector embeddings in PostgreSQL.

Table: datamind_agents.semantic_facts (pgvector 1024-dim, cosine similarity)
Protocols: None
SOLID: SRP (pgvector semantic facts only), OCP (IMemoryStore subclass)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.memory.base import IMemoryStore
from rag_api.models import MemoryEntry, MemoryTier

log = structlog.get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS datamind_agents.semantic_facts (
    fact_id     TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    agent_id    TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    embedding   vector(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS semantic_facts_tenant_idx
    ON datamind_agents.semantic_facts (tenant_id);
CREATE INDEX IF NOT EXISTS semantic_facts_vec_idx
    ON datamind_agents.semantic_facts
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""


class PgVectorSemanticStore(IMemoryStore):
    """Semantic Facts backed by PostgreSQL with pgvector.

    Facts are embedded via the embedding service and stored with a
    1024-dim vector column. Retrieval uses ``<=>`` (cosine distance) for
    approximate nearest-neighbour search.

    Attributes:
        _pool: asyncpg connection pool.
        _http: Async HTTP client for embedding service.
        _settings: Service configuration.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,  # type: ignore[type-arg]
        http: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._http = http
        self._settings = settings

    async def ensure_schema(self) -> None:
        """Create the semantic_facts table and indexes if they do not exist."""
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE SCHEMA IF NOT EXISTS datamind_agents")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(_CREATE_TABLE_SQL)
            try:
                await conn.execute(_CREATE_INDEX_SQL)
            except asyncpg.UniqueViolationError:
                pass  # Indexes already exist
        log.info("semantic_facts.schema_ensured")

    # ── IMemoryStore ──────────────────────────────────────────────────────────

    async def store(self, entry: MemoryEntry) -> str:
        """Embed and insert a semantic fact.

        Args:
            entry: Memory entry to persist as a semantic fact.

        Returns:
            The fact_id (same as memory_id).
        """
        fact_id = entry.memory_id or str(uuid.uuid4())
        vector = await self._embed(entry.content)
        vector_str = _vector_to_pg(vector)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO datamind_agents.semantic_facts
                    (fact_id, tenant_id, agent_id, session_id, content, metadata, embedding, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, $8)
                ON CONFLICT (fact_id) DO UPDATE
                    SET content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                """,
                fact_id,
                entry.tenant_id,
                entry.agent_id,
                entry.session_id,
                entry.content,
                _metadata_to_json(entry.metadata),
                vector_str,
                entry.created_at,
            )

        log.debug("semantic_facts.stored", fact_id=fact_id, tenant_id=entry.tenant_id)
        return fact_id

    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve semantically similar facts using pgvector cosine distance.

        Args:
            tenant_id: Tenant isolation key.
            agent_id: Not used for filtering (all agent facts within tenant).
            query: Natural language query to embed and compare.
            top_k: Max entries to return.

        Returns:
            Matching MemoryEntry list ordered by cosine similarity (closest first).
        """
        vector = await self._embed(query)
        vector_str = _vector_to_pg(vector)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fact_id, tenant_id, agent_id, session_id,
                       content, metadata, created_at,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM datamind_agents.semantic_facts
                WHERE tenant_id = $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                vector_str,
                tenant_id,
                top_k,
            )

        return [_row_to_entry(r) for r in rows]

    async def delete(self, tenant_id: str, memory_id: str) -> bool:
        """Delete a specific semantic fact.

        Args:
            tenant_id: Tenant isolation key.
            memory_id: Fact ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM datamind_agents.semantic_facts "
                "WHERE tenant_id = $1 AND fact_id = $2",
                tenant_id,
                memory_id,
            )
        return result.split()[-1] != "0"

    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete ALL semantic facts for a tenant (GDPR Art.17 erasure).

        Args:
            tenant_id: Tenant whose facts to erase.

        Returns:
            Count of deleted rows.
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM datamind_agents.semantic_facts WHERE tenant_id = $1",
                tenant_id,
            )
        # asyncpg returns "DELETE N"
        deleted = int(result.split()[-1])
        log.info("semantic_facts.tenant_erased", tenant_id=tenant_id, deleted=deleted)
        return deleted

    # ── Internal ──────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _embed(self, text: str) -> list[float]:
        """Call embedding service to vectorise text.

        Args:
            text: Text to embed.

        Returns:
            1024-dimensional embedding vector.
        """
        response = await self._http.post(
            f"{self._settings.embedding_service_url}/embed",
            json={"texts": [text]},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _vector_to_pg(vector: list[float]) -> str:
    """Convert a Python list to PostgreSQL vector literal string."""
    return "[" + ",".join(str(v) for v in vector) + "]"


def _metadata_to_json(metadata: dict[str, Any]) -> str:
    import json
    return json.dumps(metadata)


def _row_to_entry(row: asyncpg.Record) -> MemoryEntry:  # type: ignore[type-arg]
    """Convert an asyncpg row to MemoryEntry."""
    import json
    metadata_raw = row["metadata"]
    if isinstance(metadata_raw, str):
        try:
            metadata = json.loads(metadata_raw)
        except (json.JSONDecodeError, TypeError):
            metadata = {}
    elif isinstance(metadata_raw, dict):
        metadata = metadata_raw
    else:
        metadata = {}

    created_at: datetime = row["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return MemoryEntry(
        memory_id=str(row["fact_id"]),
        tenant_id=str(row["tenant_id"]),
        agent_id=str(row["agent_id"]),
        session_id=str(row["session_id"]),
        content=str(row["content"]),
        metadata=metadata,
        tier=MemoryTier.SEMANTIC,
        created_at=created_at,
    )
