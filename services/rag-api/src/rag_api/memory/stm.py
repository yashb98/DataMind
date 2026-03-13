"""
RAG API — Redis Short-Term Memory (STM).
Day 22: Phase 5 — 30-minute TTL working memory for active agent sessions.

Key pattern: rag:stm:{tenant_id}:{memory_id}
Protocols: None
SOLID: SRP (Redis STM only), OCP (IMemoryStore subclass)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from redis.asyncio import Redis

from rag_api.config import Settings
from rag_api.memory.base import IMemoryStore
from rag_api.models import MemoryEntry, MemoryTier

log = structlog.get_logger(__name__)

_KEY_PREFIX = "rag:stm"


class RedisSTMStore(IMemoryStore):
    """Short-Term Memory backed by Redis with configurable TTL.

    All keys follow the pattern ``rag:stm:{tenant_id}:{memory_id}``
    so tenant data is logically isolated and can be bulk-deleted efficiently.

    Attributes:
        _redis: Async Redis client.
        _ttl: TTL in seconds (default 1800 = 30 min).
    """

    def __init__(self, redis: Redis[Any], settings: Settings) -> None:
        self._redis = redis
        self._ttl = settings.stm_ttl_seconds

    # ── IMemoryStore ──────────────────────────────────────────────────────────

    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry with TTL.

        Args:
            entry: Memory entry to persist.

        Returns:
            The memory_id of the stored entry.
        """
        key = _make_key(entry.tenant_id, entry.memory_id)
        payload = entry.model_dump(mode="json")
        await self._redis.setex(key, self._ttl, json.dumps(payload))
        log.debug(
            "stm.stored",
            memory_id=entry.memory_id,
            tenant_id=entry.tenant_id,
            ttl=self._ttl,
        )
        return entry.memory_id

    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve STM entries via keyword matching.

        Scans all keys for the tenant and performs simple case-insensitive
        substring matching of the query against entry content. No embeddings
        are needed for STM: the working set is small and recency matters most.

        Args:
            tenant_id: Tenant isolation key.
            agent_id: Not used for filtering (all agent memories within tenant).
            query: Search string for substring matching.
            top_k: Max entries to return.

        Returns:
            Matching MemoryEntry list, sorted newest-first.
        """
        pattern = f"{_KEY_PREFIX}:{tenant_id}:*"
        entries: list[MemoryEntry] = []

        cursor: int = 0
        query_lower = query.lower()

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                raw = await self._redis.get(key)
                if raw is None:
                    continue
                try:
                    data = json.loads(raw)
                    entry = MemoryEntry(**data)
                    if query_lower in entry.content.lower():
                        entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    log.warning("stm.deserialize_error", key=str(key))
            if cursor == 0:
                break

        # Sort by created_at descending (newest first)
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:top_k]

    async def delete(self, tenant_id: str, memory_id: str) -> bool:
        """Delete a specific STM entry.

        Args:
            tenant_id: Tenant isolation key.
            memory_id: ID of the memory to delete.

        Returns:
            True if deleted, False if key not found.
        """
        key = _make_key(tenant_id, memory_id)
        deleted = await self._redis.delete(key)
        return bool(deleted)

    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete all STM entries for a tenant (GDPR Art.17 erasure).

        Args:
            tenant_id: Tenant whose STM data to erase.

        Returns:
            Count of deleted keys.
        """
        pattern = f"{_KEY_PREFIX}:{tenant_id}:*"
        deleted_count = 0
        cursor: int = 0

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                deleted_count += await self._redis.delete(*keys)
            if cursor == 0:
                break

        log.info("stm.tenant_erased", tenant_id=tenant_id, deleted=deleted_count)
        return deleted_count


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_key(tenant_id: str, memory_id: str) -> str:
    return f"{_KEY_PREFIX}:{tenant_id}:{memory_id}"


def make_memory_entry(
    tenant_id: str,
    agent_id: str,
    session_id: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    memory_id: str | None = None,
) -> MemoryEntry:
    """Factory helper to create a MemoryEntry for STM tier."""
    import uuid
    now = datetime.now(tz=timezone.utc)
    return MemoryEntry(
        memory_id=memory_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        agent_id=agent_id,
        session_id=session_id,
        content=content,
        metadata=metadata or {},
        tier=MemoryTier.STM,
        created_at=now,
        expires_at=None,
    )
