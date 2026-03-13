"""
RAG API — Memory Router.
Day 22: Phase 5 — 4-tier agent memory CRUD endpoints.

Endpoints:
  POST   /api/memory/store       — store in specified tiers
  POST   /api/memory/retrieve    — retrieve from tiers
  POST   /api/memory/promote     — promote STM → LTM
  DELETE /api/memory/{tenant_id} — DSR erasure (GDPR Art. 17)

Protocols: None (REST)
SOLID: SRP (routing only), DIP (MemoryManager from app.state)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from prometheus_client import Counter, Histogram

from rag_api.models import (
    DSREraseResponse,
    MemoryEntry,
    MemoryTier,
    PromoteMemoryRequest,
    PromoteMemoryResponse,
    RetrieveMemoryRequest,
    RetrieveMemoryResponse,
    StoreMemoryRequest,
    StoreMemoryResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory"])

# ── Prometheus Metrics ────────────────────────────────────────────────────────

MEMORY_OPS = Counter(
    "rag_api_memory_ops_total",
    "Memory tier operations",
    ["operation", "tier", "status"],
)
MEMORY_LATENCY = Histogram(
    "rag_api_memory_latency_ms",
    "Memory operation latency in milliseconds",
    ["operation"],
    buckets=[5, 20, 50, 100, 300, 1000],
)


# ── Dependency ────────────────────────────────────────────────────────────────


def _get_memory_manager(request: Request) -> Any:
    manager = getattr(request.app.state, "memory_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="MemoryManager not initialised")
    return manager


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/store", response_model=StoreMemoryResponse)
async def store_memory(
    body: StoreMemoryRequest,
    request: Request,
) -> StoreMemoryResponse:
    """Store a memory entry in one or more tiers.

    Args:
        body: Memory content, target tiers, and tenant context.

    Returns:
        StoreMemoryResponse with {tier: memory_id} mapping.
    """
    import time
    t0 = time.perf_counter()

    manager = _get_memory_manager(request)
    bound_log = log.bind(tenant_id=body.tenant_id, tiers=[t.value for t in body.tiers])

    memory_id = str(uuid.uuid4())
    entry = MemoryEntry(
        memory_id=memory_id,
        tenant_id=body.tenant_id,
        agent_id=body.agent_id,
        session_id=body.session_id,
        content=body.content,
        metadata=body.metadata,
        tier=body.tiers[0] if body.tiers else MemoryTier.STM,
        created_at=datetime.now(tz=timezone.utc),
    )

    try:
        memory_ids = await manager.store(entry=entry, tiers=body.tiers)
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="store").observe(elapsed)
        for tier in body.tiers:
            MEMORY_OPS.labels(operation="store", tier=tier.value, status="ok").inc()

        bound_log.info("memory.store.ok", memory_ids=memory_ids, latency_ms=round(elapsed, 1))
        return StoreMemoryResponse(memory_ids=memory_ids, tenant_id=body.tenant_id)

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="store").observe(elapsed)
        for tier in body.tiers:
            MEMORY_OPS.labels(operation="store", tier=tier.value, status="error").inc()
        bound_log.error("memory.store.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Memory store failed: {exc}") from exc


@router.post("/retrieve", response_model=RetrieveMemoryResponse)
async def retrieve_memory(
    body: RetrieveMemoryRequest,
    request: Request,
) -> RetrieveMemoryResponse:
    """Retrieve memories from specified tiers for a given query.

    Args:
        body: Query, tenant context, tiers to search, and top_k limit.

    Returns:
        RetrieveMemoryResponse with merged, deduplicated memories.
    """
    import time
    t0 = time.perf_counter()

    manager = _get_memory_manager(request)
    bound_log = log.bind(tenant_id=body.tenant_id, tiers=[t.value for t in body.tiers])

    try:
        memories = await manager.retrieve(
            tenant_id=body.tenant_id,
            agent_id=body.agent_id,
            query=body.query,
            tiers=body.tiers,
            top_k=body.top_k,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="retrieve").observe(elapsed)
        MEMORY_OPS.labels(operation="retrieve", tier="all", status="ok").inc()

        bound_log.info(
            "memory.retrieve.ok",
            count=len(memories),
            latency_ms=round(elapsed, 1),
        )
        return RetrieveMemoryResponse(
            memories=memories,
            total=len(memories),
            tiers_queried=body.tiers,
        )

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="retrieve").observe(elapsed)
        MEMORY_OPS.labels(operation="retrieve", tier="all", status="error").inc()
        bound_log.error("memory.retrieve.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Memory retrieve failed: {exc}") from exc


@router.post("/promote", response_model=PromoteMemoryResponse)
async def promote_memory(
    body: PromoteMemoryRequest,
    request: Request,
) -> PromoteMemoryResponse:
    """Promote a memory from one tier to another (e.g., STM → LTM after session end).

    Args:
        body: memory_id, from_tier, to_tier, and tenant context.

    Returns:
        PromoteMemoryResponse with the new memory_id in the destination tier.
    """
    import time
    t0 = time.perf_counter()

    manager = _get_memory_manager(request)
    bound_log = log.bind(
        tenant_id=body.tenant_id,
        memory_id=body.memory_id,
        from_tier=body.from_tier.value,
        to_tier=body.to_tier.value,
    )

    try:
        new_id = await manager.promote(
            memory_id=body.memory_id,
            from_tier=body.from_tier,
            to_tier=body.to_tier,
            tenant_id=body.tenant_id,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="promote").observe(elapsed)
        MEMORY_OPS.labels(operation="promote", tier=body.to_tier.value, status="ok").inc()

        bound_log.info("memory.promote.ok", new_id=new_id, latency_ms=round(elapsed, 1))
        return PromoteMemoryResponse(
            new_memory_id=new_id,
            from_tier=body.from_tier,
            to_tier=body.to_tier,
        )

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="promote").observe(elapsed)
        MEMORY_OPS.labels(operation="promote", tier=body.to_tier.value, status="error").inc()
        bound_log.error("memory.promote.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Memory promote failed: {exc}") from exc


@router.delete("/{tenant_id}", response_model=DSREraseResponse)
async def erase_tenant_memory(
    tenant_id: str,
    request: Request,
) -> DSREraseResponse:
    """GDPR Art.17 erasure — delete ALL memories for a tenant across all tiers.

    This endpoint is called by the DSR router as part of Subject Erasure Request
    processing. SLA: complete within 72 hours.

    Args:
        tenant_id: Tenant whose memory data to erase.

    Returns:
        DSREraseResponse with per-tier deletion counts.
    """
    import time
    t0 = time.perf_counter()

    manager = _get_memory_manager(request)
    bound_log = log.bind(tenant_id=tenant_id)
    bound_log.info("memory.dsr_erase.start")

    try:
        counts = await manager.delete_tenant(tenant_id=tenant_id)
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="dsr_erase").observe(elapsed)
        MEMORY_OPS.labels(operation="dsr_erase", tier="all", status="ok").inc()

        total = sum(counts.values())
        bound_log.info(
            "memory.dsr_erase.ok",
            total=total,
            counts=counts,
            latency_ms=round(elapsed, 1),
        )
        return DSREraseResponse(
            tenant_id=tenant_id,
            deleted=counts,
            total_deleted=total,
        )

    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        MEMORY_LATENCY.labels(operation="dsr_erase").observe(elapsed)
        MEMORY_OPS.labels(operation="dsr_erase", tier="all", status="error").inc()
        bound_log.error("memory.dsr_erase.failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Memory DSR erase failed: {exc}") from exc
