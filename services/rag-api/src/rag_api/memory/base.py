"""
RAG API — IMemoryStore ABC.
Day 22: Phase 5 — Abstract base for all 4 memory tiers.

Protocols: None
SOLID: OCP (each tier is a new subclass), ISP (minimal interface), LSP (all impls return MemoryEntry)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rag_api.models import MemoryEntry


class IMemoryStore(ABC):
    """Abstract interface for a single memory tier.

    All implementations must be tenant-isolated: every read/write/delete
    filters by tenant_id to enforce multi-tenancy.
    """

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Persist a memory entry.

        Args:
            entry: The memory entry to persist.

        Returns:
            The memory_id of the stored entry.
        """
        ...

    @abstractmethod
    async def retrieve(
        self,
        tenant_id: str,
        agent_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories for a query.

        Args:
            tenant_id: Tenant isolation key.
            agent_id: The requesting agent.
            query: Natural language search query.
            top_k: Max number of entries to return.

        Returns:
            List of matching MemoryEntry objects ordered by relevance/recency.
        """
        ...

    @abstractmethod
    async def delete(self, tenant_id: str, memory_id: str) -> bool:
        """Delete a specific memory entry.

        Args:
            tenant_id: Tenant isolation key.
            memory_id: ID of the memory to delete.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete ALL memories for a tenant (GDPR Art.17 erasure).

        Args:
            tenant_id: Tenant whose data to erase.

        Returns:
            Count of deleted entries.
        """
        ...
