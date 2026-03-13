"""
RAG API — MongoDB Episodic Memory.
Day 22: Phase 5 — Event-ordered memory with 1-year TTL for agent experience replay.

Collection: episodic_memory (MongoDB, TTL index on expires_at)
Protocols: None
SOLID: SRP (MongoDB episodic only), OCP (IMemoryStore subclass)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from rag_api.config import Settings
from rag_api.memory.base import IMemoryStore
from rag_api.models import MemoryEntry, MemoryTier

log = structlog.get_logger(__name__)


class MongoEpisodicStore(IMemoryStore):
    """Episodic Memory backed by MongoDB with 1-year TTL.

    MongoDB's native TTL index (``expireAfterSeconds: 0`` on ``expires_at``)
    handles automatic expiry. Text search uses a compound index on
    ``tenant_id + content`` for efficient filtering.

    Attributes:
        _db: Async Motor database handle.
        _settings: Service configuration.
    """

    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings) -> None:  # type: ignore[type-arg]
        self._db = db
        self._settings = settings
        self._collection_name = settings.episodic_collection

    @property
    def _col(self):  # type: ignore[no-untyped-def]
        return self._db[self._collection_name]

    async def ensure_indexes(self) -> None:
        """Create TTL and text search indexes on first startup."""
        # TTL index — MongoDB auto-deletes documents when expires_at is reached
        await self._col.create_index("expires_at", expireAfterSeconds=0)
        # Compound index for tenant-scoped queries
        await self._col.create_index([("tenant_id", 1), ("created_at", -1)])
        # Text index for keyword search on content
        await self._col.create_index([("content", "text")])
        log.info("episodic.indexes_ensured", collection=self._collection_name)

    # ── IMemoryStore ──────────────────────────────────────────────────────────

    async def store(self, entry: MemoryEntry) -> str:
        """Insert an episodic memory with TTL.

        Args:
            entry: Memory entry to persist.

        Returns:
            The memory_id of the inserted document.
        """
        memory_id = entry.memory_id or str(uuid.uuid4())
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            days=self._settings.episodic_ttl_days
        )
        doc: dict[str, Any] = {
            **entry.model_dump(mode="json"),
            "memory_id": memory_id,
            "expires_at": expires_at,
        }
        await self._col.insert_one(doc)
        log.debug(
            "episodic.stored",
            memory_id=memory_id,
            tenant_id=entry.tenant_id,
            expires_at=expires_at.isoformat(),
        )
        return memory_id

    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve episodic memories via MongoDB text search.

        Falls back to a recency-ordered scan if no text-indexed documents match.

        Args:
            tenant_id: Tenant isolation key.
            agent_id: Not used for filtering (all agent memories within tenant).
            query: Natural language search query.
            top_k: Max entries to return.

        Returns:
            Matching MemoryEntry list, sorted newest-first.
        """
        base_filter: dict[str, Any] = {"tenant_id": tenant_id}

        # Try text search first
        text_filter: dict[str, Any] = {
            **base_filter,
            "$text": {"$search": query},
        }
        cursor = self._col.find(
            text_filter,
            {"score": {"$meta": "textScore"}},
        ).sort([("score", {"$meta": "textScore"})]).limit(top_k)

        docs = await cursor.to_list(length=top_k)

        # Fallback: recency scan if text search returns nothing
        if not docs:
            fallback_cursor = (
                self._col.find(base_filter)
                .sort("created_at", -1)
                .limit(top_k)
            )
            docs = await fallback_cursor.to_list(length=top_k)

        return [_doc_to_entry(d) for d in docs]

    async def delete(self, tenant_id: str, memory_id: str) -> bool:
        """Delete a specific episodic memory.

        Args:
            tenant_id: Tenant isolation key.
            memory_id: ID of the memory to delete.

        Returns:
            True if a document was deleted, False if not found.
        """
        result = await self._col.delete_one(
            {"tenant_id": tenant_id, "memory_id": memory_id}
        )
        return result.deleted_count > 0

    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete ALL episodic memories for a tenant (GDPR Art.17 erasure).

        Args:
            tenant_id: Tenant whose MongoDB data to erase.

        Returns:
            Count of deleted documents.
        """
        result = await self._col.delete_many({"tenant_id": tenant_id})
        deleted = result.deleted_count
        log.info("episodic.tenant_erased", tenant_id=tenant_id, deleted=deleted)
        return deleted


# ── Helpers ───────────────────────────────────────────────────────────────────


def _doc_to_entry(doc: dict[str, Any]) -> MemoryEntry:
    """Convert a MongoDB document to a MemoryEntry."""
    # Remove MongoDB-specific fields
    doc.pop("_id", None)
    doc.pop("score", None)
    doc.pop("expires_at", None)

    created_at = doc.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            created_at = datetime.now(tz=timezone.utc)
    elif not isinstance(created_at, datetime):
        created_at = datetime.now(tz=timezone.utc)

    return MemoryEntry(
        memory_id=str(doc.get("memory_id", "")),
        tenant_id=str(doc.get("tenant_id", "")),
        agent_id=str(doc.get("agent_id", "")),
        session_id=str(doc.get("session_id", "")),
        content=str(doc.get("content", "")),
        metadata=dict(doc.get("metadata", {})),
        tier=MemoryTier.EPISODIC,
        created_at=created_at,
        expires_at=None,
    )
