"""
Health check router — liveness + readiness probes.
Used by Kubernetes, Docker Compose healthchecks, and Prometheus.
"""
import asyncio
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from datamind_api.config import settings

log = structlog.get_logger(__name__)
router = APIRouter()


class ServiceHealth(BaseModel):
    name: str
    status: str  # "healthy" | "degraded" | "unhealthy"
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    services: list[ServiceHealth]


async def _check_http(name: str, url: str, timeout: float = 3.0) -> ServiceHealth:
    try:
        start = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        latency = (asyncio.get_event_loop().time() - start) * 1000
        if resp.status_code < 400:
            return ServiceHealth(name=name, status="healthy", latency_ms=round(latency, 1))
        return ServiceHealth(name=name, status="degraded", latency_ms=round(latency, 1), detail=f"HTTP {resp.status_code}")
    except Exception as e:
        return ServiceHealth(name=name, status="unhealthy", detail=str(e)[:100])


@router.get("/liveness", status_code=200)
async def liveness():
    """Kubernetes liveness probe — always 200 if process is alive."""
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/readiness", response_model=HealthResponse)
async def readiness():
    """Kubernetes readiness probe — checks all dependency health."""
    checks = await asyncio.gather(
        _check_http("litellm", f"{settings.litellm_proxy_url}/health/liveliness"),
        _check_http("langfuse", f"{settings.langfuse_host}/api/public/health"),
        _check_http("qdrant", f"{settings.qdrant_url}/health"),
        _check_http("ollama", f"{settings.ollama_url}/api/tags"),
        _check_http("presidio-analyzer", f"{settings.presidio_analyzer_url}/health"),
        return_exceptions=False,
    )

    services = list(checks)
    overall = "healthy" if all(s.status == "healthy" for s in services) else (
        "degraded" if any(s.status == "healthy" for s in services) else "unhealthy"
    )

    log.info("health.readiness", overall=overall, services={s.name: s.status for s in services})

    return HealthResponse(
        status=overall,
        version="0.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
    )
