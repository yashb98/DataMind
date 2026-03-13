"""
RAG API — Unit tests for memory tier implementations.
Day 22: Phase 5 — Tests for IMemoryStore implementations and MemoryManager.

Coverage target: ≥80%
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_api.memory.base import IMemoryStore
from rag_api.memory.stm import RedisSTMStore, make_memory_entry
from rag_api.memory.manager import MemoryManager
from rag_api.models import MemoryEntry, MemoryTier


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_entry(
    content: str = "test content",
    tier: MemoryTier = MemoryTier.STM,
    memory_id: str = "mem-001",
    tenant_id: str = "tenant-a",
) -> MemoryEntry:
    return MemoryEntry(
        memory_id=memory_id,
        tenant_id=tenant_id,
        agent_id="aria",
        session_id="sess-001",
        content=content,
        metadata={"source": "test"},
        tier=tier,
        created_at=datetime.now(tz=timezone.utc),
    )


# ── IMemoryStore ABC ──────────────────────────────────────────────────────────


def test_memory_store_abc_cannot_instantiate() -> None:
    """IMemoryStore is abstract and cannot be directly instantiated."""
    with pytest.raises(TypeError):
        IMemoryStore()  # type: ignore[abstract]


# ── RedisSTMStore ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_stm_store_and_retrieve() -> None:
    """STM store persists an entry and retrieves it by content match."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(return_value=True)

    # Simulate SCAN returning one key, then end
    mock_redis.scan = AsyncMock(
        side_effect=[
            (0, [b"rag:stm:tenant-a:mem-001"]),
        ]
    )

    import json
    from datetime import datetime, timezone
    entry = _make_entry(content="quarterly revenue report")
    mock_redis.get = AsyncMock(return_value=json.dumps(entry.model_dump(mode="json")).encode())

    from rag_api.config import Settings
    settings = Settings()
    store = RedisSTMStore(redis=mock_redis, settings=settings)  # type: ignore[arg-type]

    # Store
    mem_id = await store.store(entry)
    assert mem_id == "mem-001"
    mock_redis.setex.assert_called_once()

    # Retrieve
    results = await store.retrieve(
        tenant_id="tenant-a",
        agent_id="aria",
        query="revenue",
        top_k=5,
    )
    assert len(results) == 1
    assert results[0].content == "quarterly revenue report"


@pytest.mark.asyncio
async def test_redis_stm_delete() -> None:
    """STM delete removes the key and returns True."""
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=1)

    from rag_api.config import Settings
    store = RedisSTMStore(redis=mock_redis, settings=Settings())  # type: ignore[arg-type]
    deleted = await store.delete("tenant-a", "mem-001")

    assert deleted is True
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_redis_stm_delete_tenant() -> None:
    """STM delete_tenant scans and deletes all tenant keys."""
    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(
        side_effect=[
            (0, [b"rag:stm:tenant-a:m1", b"rag:stm:tenant-a:m2"]),
        ]
    )
    mock_redis.delete = AsyncMock(return_value=2)

    from rag_api.config import Settings
    store = RedisSTMStore(redis=mock_redis, settings=Settings())  # type: ignore[arg-type]
    count = await store.delete_tenant("tenant-a")

    assert count == 2


# ── make_memory_entry helper ──────────────────────────────────────────────────


def test_make_memory_entry_defaults() -> None:
    """make_memory_entry creates a valid MemoryEntry with STM tier."""
    entry = make_memory_entry(
        tenant_id="t1",
        agent_id="aria",
        session_id="s1",
        content="hello",
    )
    assert entry.tenant_id == "t1"
    assert entry.tier == MemoryTier.STM
    assert entry.memory_id is not None
    assert len(entry.memory_id) == 36  # UUID length


# ── MemoryManager ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_manager_store_stm_only() -> None:
    """MemoryManager.store delegates to STM store only when tiers=[STM]."""
    mock_stm = AsyncMock()
    mock_stm.store = AsyncMock(return_value="mem-abc")

    mock_ltm = AsyncMock()
    mock_episodic = AsyncMock()
    mock_semantic = AsyncMock()

    manager = MemoryManager(
        stm=mock_stm,  # type: ignore[arg-type]
        ltm=mock_ltm,  # type: ignore[arg-type]
        episodic=mock_episodic,  # type: ignore[arg-type]
        semantic=mock_semantic,  # type: ignore[arg-type]
    )

    entry = _make_entry()
    result = await manager.store(entry=entry, tiers=[MemoryTier.STM])

    assert "stm" in result
    mock_stm.store.assert_awaited_once()
    mock_ltm.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_manager_retrieve_merges_tiers() -> None:
    """MemoryManager.retrieve merges results from multiple tiers."""
    entry_stm = _make_entry(content="stm memory", tier=MemoryTier.STM, memory_id="s1")
    entry_ltm = _make_entry(content="ltm memory", tier=MemoryTier.LTM, memory_id="l1")

    mock_stm = AsyncMock()
    mock_stm.retrieve = AsyncMock(return_value=[entry_stm])

    mock_ltm = AsyncMock()
    mock_ltm.retrieve = AsyncMock(return_value=[entry_ltm])

    mock_episodic = AsyncMock()
    mock_episodic.retrieve = AsyncMock(return_value=[])

    mock_semantic = AsyncMock()

    manager = MemoryManager(
        stm=mock_stm,  # type: ignore[arg-type]
        ltm=mock_ltm,  # type: ignore[arg-type]
        episodic=mock_episodic,  # type: ignore[arg-type]
        semantic=mock_semantic,  # type: ignore[arg-type]
    )

    results = await manager.retrieve(
        tenant_id="t1",
        agent_id="aria",
        query="memory",
        tiers=[MemoryTier.STM, MemoryTier.LTM, MemoryTier.EPISODIC],
        top_k=10,
    )

    assert len(results) == 2
    contents = {r.content for r in results}
    assert "stm memory" in contents
    assert "ltm memory" in contents


@pytest.mark.asyncio
async def test_memory_manager_delete_tenant_all_tiers() -> None:
    """MemoryManager.delete_tenant calls delete_tenant on all 4 stores."""
    mock_stm = AsyncMock()
    mock_stm.delete_tenant = AsyncMock(return_value=5)
    mock_ltm = AsyncMock()
    mock_ltm.delete_tenant = AsyncMock(return_value=1)
    mock_episodic = AsyncMock()
    mock_episodic.delete_tenant = AsyncMock(return_value=3)
    mock_semantic = AsyncMock()
    mock_semantic.delete_tenant = AsyncMock(return_value=2)

    manager = MemoryManager(
        stm=mock_stm,  # type: ignore[arg-type]
        ltm=mock_ltm,  # type: ignore[arg-type]
        episodic=mock_episodic,  # type: ignore[arg-type]
        semantic=mock_semantic,  # type: ignore[arg-type]
    )

    counts = await manager.delete_tenant("tenant-x")

    assert counts["stm"] == 5
    assert counts["ltm"] == 1
    assert counts["episodic"] == 3
    assert counts["semantic"] == 2


# ── MemoryEntry model ─────────────────────────────────────────────────────────


def test_memory_entry_tier_values() -> None:
    """MemoryTier enum values are lowercase strings."""
    assert MemoryTier.STM.value == "stm"
    assert MemoryTier.LTM.value == "ltm"
    assert MemoryTier.EPISODIC.value == "episodic"
    assert MemoryTier.SEMANTIC.value == "semantic"


def test_memory_entry_serialization() -> None:
    """MemoryEntry serialises cleanly to JSON-compatible dict."""
    entry = _make_entry()
    data = entry.model_dump(mode="json")
    assert data["memory_id"] == "mem-001"
    assert data["tier"] == "stm"
    assert isinstance(data["created_at"], str)  # ISO format string
