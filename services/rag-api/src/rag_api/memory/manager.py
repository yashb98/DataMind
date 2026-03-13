"""
RAG API — MemoryManager: 4-Tier Memory Orchestrator.
Day 22: Phase 5 — Routes memory operations across STM, LTM, Episodic, and Semantic tiers.

Protocols: None
SOLID: SRP (routing only — stores handle persistence), DIP (stores injected), OCP (add tiers via new IMemoryStore)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from rag_api.memory.base import IMemoryStore
from rag_api.memory.episodic import MongoEpisodicStore
from rag_api.memory.ltm import QdrantLTMStore
from rag_api.memory.semantic_facts import PgVectorSemanticStore
from rag_api.memory.stm import RedisSTMStore
from rag_api.models import MemoryEntry, MemoryTier

log = structlog.get_logger(__name__)


class MemoryManager:
    """Orchestrates read/write operations across all 4 memory tiers.

    The Manager's only responsibility is routing: it delegates to the
    appropriate IMemoryStore implementations and merges results. It does
    not contain any persistence logic (SRP).

    Attributes:
        _stores: Mapping from MemoryTier to IMemoryStore implementation.
    """

    def __init__(
        self,
        stm: RedisSTMStore,
        ltm: QdrantLTMStore,
        episodic: MongoEpisodicStore,
        semantic: PgVectorSemanticStore,
    ) -> None:
        self._stores: dict[MemoryTier, IMemoryStore] = {
            MemoryTier.STM: stm,
            MemoryTier.LTM: ltm,
            MemoryTier.EPISODIC: episodic,
            MemoryTier.SEMANTIC: semantic,
        }

    async def store(
        self,
        entry: MemoryEntry,
        tiers: list[MemoryTier] | None = None,
    ) -> dict[str, str]:
        """Store memory in specified tiers.

        Creates a new MemoryEntry per tier (different tier label, same content)
        so each store receives a well-typed entry.

        Args:
            entry: Source memory entry (tier field overridden per destination).
            tiers: Which tiers to write to. Defaults to [STM].

        Returns:
            Mapping of {tier_name: memory_id} for each tier written.
        """
        if tiers is None:
            tiers = [MemoryTier.STM]

        results: dict[str, str] = {}

        for tier in tiers:
            store = self._stores.get(tier)
            if store is None:
                log.warning("memory_manager.unknown_tier", tier=tier)
                continue

            # Each tier gets a tiered copy of the entry
            tier_entry = entry.model_copy(
                update={
                    "memory_id": entry.memory_id or str(uuid.uuid4()),
                    "tier": tier,
                }
            )
            try:
                memory_id = await store.store(tier_entry)
                results[tier.value] = memory_id
                log.debug(
                    "memory_manager.stored",
                    tier=tier.value,
                    memory_id=memory_id,
                    tenant_id=entry.tenant_id,
                )
            except Exception as exc:
                log.error(
                    "memory_manager.store_failed",
                    tier=tier.value,
                    tenant_id=entry.tenant_id,
                    error=str(exc),
                )

        return results

    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        tiers: list[MemoryTier] | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve from specified tiers, merge by recency, deduplicate.

        Queries each tier concurrently (via gather), merges all results,
        deduplicates by content hash, and returns the top_k most recent entries.

        Args:
            tenant_id: Tenant isolation key.
            agent_id: Requesting agent.
            query: Natural language search query.
            tiers: Which tiers to query. Defaults to [STM, LTM, EPISODIC].
            top_k: Max total entries to return.

        Returns:
            Merged, deduplicated MemoryEntry list sorted newest-first.
        """
        import asyncio

        if tiers is None:
            tiers = [MemoryTier.STM, MemoryTier.LTM, MemoryTier.EPISODIC]

        async def _fetch_tier(tier: MemoryTier) -> list[MemoryEntry]:
            store = self._stores.get(tier)
            if store is None:
                return []
            try:
                return await store.retrieve(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    query=query,
                    top_k=top_k,
                )
            except Exception as exc:
                log.error(
                    "memory_manager.retrieve_failed",
                    tier=tier.value,
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                return []

        tier_results = await asyncio.gather(*[_fetch_tier(t) for t in tiers])

        # Flatten + deduplicate by content fingerprint
        seen: set[str] = set()
        merged: list[MemoryEntry] = []
        for entries in tier_results:
            for entry in entries:
                fingerprint = f"{entry.tenant_id}:{entry.content[:128]}"
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    merged.append(entry)

        # Sort by created_at descending (newest first)
        merged.sort(
            key=lambda e: e.created_at if e.created_at.tzinfo else e.created_at.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return merged[:top_k]

    async def promote(
        self,
        memory_id: str,
        from_tier: MemoryTier,
        to_tier: MemoryTier,
        tenant_id: str,
    ) -> str:
        """Promote a memory from one tier to another (e.g., STM → LTM after session end).

        Retrieves the entry from the source tier via a direct Redis key lookup
        (STM case) or a metadata search, writes it to the target tier, and
        optionally deletes from source.

        Args:
            memory_id: ID of the memory to promote.
            from_tier: Source tier to read from.
            to_tier: Destination tier to write to.
            tenant_id: Tenant isolation key.

        Returns:
            New memory_id in the destination tier.

        Raises:
            ValueError: If the memory is not found in the source tier.
        """
        source_store = self._stores.get(from_tier)
        target_store = self._stores.get(to_tier)

        if source_store is None or target_store is None:
            raise ValueError(f"Unknown tier: {from_tier} or {to_tier}")

        # Retrieve all from source to find the specific entry
        # For STM we do a wildcard scan; for others a content-based search
        candidates = await source_store.retrieve(
            tenant_id=tenant_id,
            agent_id="",
            query=memory_id,  # memory_id substring search for STM
            top_k=50,
        )

        entry = next((e for e in candidates if e.memory_id == memory_id), None)

        if entry is None:
            raise ValueError(f"Memory {memory_id} not found in tier {from_tier}")

        # Write to target tier
        promoted_entry = entry.model_copy(
            update={
                "memory_id": str(uuid.uuid4()),
                "tier": to_tier,
                "created_at": datetime.now(tz=timezone.utc),
            }
        )
        new_id = await target_store.store(promoted_entry)

        log.info(
            "memory_manager.promoted",
            from_tier=from_tier.value,
            to_tier=to_tier.value,
            old_id=memory_id,
            new_id=new_id,
            tenant_id=tenant_id,
        )
        return new_id

    async def delete_tenant(self, tenant_id: str) -> dict[str, int]:
        """DSR erasure: delete ALL memories across all tiers for a tenant.

        Runs deletions concurrently for maximum throughput.

        Args:
            tenant_id: Tenant whose data to erase.

        Returns:
            Mapping of {tier_name: count_deleted}.
        """
        import asyncio

        async def _erase_tier(tier: MemoryTier, store: IMemoryStore) -> tuple[str, int]:
            try:
                count = await store.delete_tenant(tenant_id)
                return tier.value, count
            except Exception as exc:
                log.error(
                    "memory_manager.erase_failed",
                    tier=tier.value,
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                return tier.value, 0

        results = await asyncio.gather(
            *[_erase_tier(tier, store) for tier, store in self._stores.items()]
        )

        counts = dict(results)
        log.info(
            "memory_manager.tenant_erased",
            tenant_id=tenant_id,
            counts=counts,
        )
        return counts
