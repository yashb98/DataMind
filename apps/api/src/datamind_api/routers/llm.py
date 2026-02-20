"""
LLM router — proxies to LiteLLM with Langfuse tracing.
Day 1 skeleton: completion + streaming endpoints.
"""
import httpx
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langfuse import Langfuse
from pydantic import BaseModel

from datamind_api.config import settings

log = structlog.get_logger(__name__)
router = APIRouter()

langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)


class CompletionRequest(BaseModel):
    model: str = "claude-sonnet-4-6"
    messages: list[dict]
    max_tokens: int = 4096
    stream: bool = False
    tenant_id: str | None = None
    metadata: dict | None = None


@router.post("/complete")
async def complete(req: CompletionRequest):
    """Non-streaming LLM completion via LiteLLM proxy."""
    trace = langfuse.trace(
        name="api.llm.complete",
        metadata={"tenant_id": req.tenant_id, "model": req.model},
    )
    span = trace.span(name="litellm.proxy.call")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.litellm_proxy_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                json={
                    "model": req.model,
                    "messages": req.messages,
                    "max_tokens": req.max_tokens,
                    "stream": False,
                    "metadata": {"trace_id": trace.id, "tenant_id": req.tenant_id},
                },
            )
        response.raise_for_status()
        result = response.json()
        span.end(output=result.get("choices", [{}])[0].get("message", {}).get("content", ""))
        return result

    except httpx.HTTPError as e:
        span.end(level="ERROR", status_message=str(e))
        log.error("llm.complete.error", error=str(e))
        raise HTTPException(status_code=502, detail=f"LLM proxy error: {e}")


@router.post("/stream")
async def stream_complete(req: CompletionRequest):
    """Streaming LLM completion — SSE response."""
    trace = langfuse.trace(name="api.llm.stream", metadata={"model": req.model})

    async def generate():
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{settings.litellm_proxy_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                json={
                    "model": req.model,
                    "messages": req.messages,
                    "max_tokens": req.max_tokens,
                    "stream": True,
                    "metadata": {"trace_id": trace.id},
                },
            ) as response:
                async for chunk in response.aiter_text():
                    yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")
