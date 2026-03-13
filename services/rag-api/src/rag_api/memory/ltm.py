"""
RAG API — Qdrant Long-Term Memory (LTM).
Day 22: Phase 5 — Semantic vector store for persistent agent memory.

Collection: agent_memory (1024-dim BAAI/bge-m3, HNSW, INT8 quantisation)
Protocols: None
SOLID: SRP (Qdrant LTM only), OCP (IMemoryStore subclass), DIP (client injected)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
    Distance,
)
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.memory.base import IMemoryStore
from rag_api.models import MemoryEntry, MemoryTier

log = structlog.get_logger(__name__)


class QdrantLTMStore(IMemoryStore):
    """Long-Term Memory backed by Qdrant vector database.

    Embeds memory content via the embedding service and stores it in the
    ``agent_memory`` collection. Retrieval uses cosine similarity with
    mandatory tenant_id payload filtering for multi-tenant isolation.

    Attributes:
        _qdrant: Async Qdrant client.
        _http: Async HTTP client for embedding service calls.
        _settings: Service configuration.
    """

    def __init__(
        self,
        qdrant: AsyncQdrantClient,
        http: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self._qdrant = qdrant
        self._http = http
        self._settings = settings

    async def ensure_collection(self) -> None:
        """Create ``agent_memory`` collection if it does not exist."""
        try:
            await self._qdrant.get_collection(self._settings.ltm_collection)
        except Exception:
            await self._qdrant.create_collection(
                collection_name=self._settings.ltm_collection,
                vectors_config=VectorParams(
                    size=self._settings.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            log.info("ltm.collection_created", collection=self._settings.ltm_collection)

    # ── IMemoryStore ──────────────────────────────────────────────────────────

    async def store(self, entry: MemoryEntry) -> str:
        """Embed and upsert a memory entry into Qdrant.

        Args:
            entry: Memory entry to persist.

        Returns:
            The memory_id used as the Qdrant point ID.
        """
        vector = await self._embed(entry.content)
        payload: dict[str, Any] = {
            "memory_id": entry.memory_id,
            "tenant_id": entry.tenant_id,
            "agent_id": entry.agent_id,
            "session_id": entry.session_id,
            "content": entry.content,
            "tier": entry.tier.value,
            "created_at": entry.created_at.isoformat(),
            **entry.metadata,
        }

        await self._qdrant.upsert(
            collection_name=self._settings.ltm_collection,
            points=[
                PointStruct(
                    id=str(uuid.UUID(entry.memory_id))
                    if _is_valid_uuid(entry.memory_id)
                    else str(uuid.uuid5(uuid.NAMESPACE_DNS, entry.memory_id)),
                    vector=vector,
                    payload=payload,
                )
            ],
        )
        log.debug("ltm.stored", memory_id=entry.memory_id, tenant_id=entry.tenant_id)
        return entry.memory_id

    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve semantically similar memories from Qdrant.

        Args:
            tenant_id: Tenant isolation key (enforced via payload filter).
            agent_id: Not used for additional filtering (all agents in tenant).
            query: Natural language search query (embedded for similarity search).
            top_k: Max entries to return.

        Returns:
            Matching MemoryEntry list ordered by cosine similarity.
        """
        vector = await self._embed(query)
        tenant_filter = Filter(
            must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        )

        results = await self._qdrant.search(
            collection_name=self._settings.ltm_collection,
            query_vector=vector,
            query_filter=tenant_filter,
            limit=top_k,
            with_payload=True,
        )

        entries: list[MemoryEntry] = []
        for hit in results:
            payload = hit.payload or {}
            try:
                created_at = datetime.fromisoformat(str(payload.get("created_at", "")))
            except (ValueError, TypeError):
                created_at = datetime.now(tz=timezone.utc)

            entries.append(
                MemoryEntry(
                    memory_id=str(payload.get("memory_id", str(hit.id))),
                    tenant_id=str(payload.get("tenant_id", tenant_id)),
                    agent_id=str(payload.get("agent_id", agent_id)),
                    session_id=str(payload.get("session_id", "")),
                    content=str(payload.get("content", "")),
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k
                        not in (
                            "memory_id",
                            "tenant_id",
                            "agent_id",
                            "session_id",
                            "content",
                            "tier",
                            "created_at",
                        )
                    },
                    tier=MemoryTier.LTM,
                    created_at=created_at,
                )
            )

        return entries

    async def delete(self, tenant_id: str, memory_id: str) -> bool:
        """Delete a specific LTM entry by memory_id payload filter.

        Args:
            tenant_id: Tenant isolation key.
            memory_id: ID of the memory to delete.

        Returns:
            True if operation completed (Qdrant does not report missing IDs).
        """
        await self._qdrant.delete(
            collection_name=self._settings.ltm_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                        FieldCondition(key="memory_id", match=MatchValue(value=memory_id)),
                    ]
                )
            ),
        )
        return True

    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete ALL LTM entries for a tenant (GDPR Art.17 erasure).

        Args:
            tenant_id: Tenant whose Qdrant data to erase.

        Returns:
            Always returns 1 (Qdrant bulk-delete does not count rows).
        """
        await self._qdrant.delete(
            collection_name=self._settings.ltm_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
                    ]
                )
            ),
        )
        log.info("ltm.tenant_erased", tenant_id=tenant_id)
        return 1  # Qdrant bulk-delete returns operation result, not count

    # ── Internal ──────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _embed(self, text: str) -> list[float]:
        """Call embedding service to vectorise text.

        Args:
            text: Text to embed.

        Returns:
            1024-dimensional embedding vector.

        Raises:
            httpx.HTTPStatusError: If embedding service returns an error.
        """
        response = await self._http.post(
            f"{self._settings.embedding_service_url}/embed",
            json={"texts": [text]},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
