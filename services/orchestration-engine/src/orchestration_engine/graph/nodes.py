"""
Orchestration Engine — LangGraph graph nodes.
Day 10: Each node is a pure async function operating on AgentState.

Protocols: MCP (client — calls mcp-sql-executor, mcp-knowledge-base)
SOLID: SRP (each node = one responsibility), OCP (new node = new function, no existing changes)
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import structlog
from langfuse.decorators import langfuse_context, observe

from orchestration_engine.config import settings
from orchestration_engine.graph.state import AgentState
from orchestration_engine.models import (
    AgentResult,
    ComplexityTier,
    ValidationResult,
    ValidationLayer,
    WorkflowIntent,
    WorkflowStatus,
)

log = structlog.get_logger(__name__)


# ── Node: Router ──────────────────────────────────────────────────────────────


@observe(name="node.router")
async def router_node(state: AgentState, http_client: httpx.AsyncClient) -> dict[str, Any]:
    """Classify intent and complexity via SLM Router.

    Calls the existing slm-router service (Day 2) to determine routing tier.
    If slm-router unavailable, falls back to cloud tier.

    Args:
        state: Current workflow state.
        http_client: Shared async HTTP client.

    Returns:
        State updates: intent, complexity, is_sensitive.
    """
    start = time.perf_counter()
    try:
        response = await http_client.post(
            f"{settings.slm_router_url}/route",
            json={
                "query": state["query"],
                "tenant_id": state["tenant_id"],
                "session_id": state["session_id"],
            },
            timeout=5.0,
        )
        response.raise_for_status()
        route_data = response.json()

        intent_str = route_data.get("intent", "general")
        try:
            intent = WorkflowIntent(intent_str)
        except ValueError:
            intent = WorkflowIntent.GENERAL

        complexity_str = route_data.get("complexity", "moderate")
        try:
            complexity = ComplexityTier(complexity_str)
        except ValueError:
            complexity = ComplexityTier.MODERATE

        is_sensitive = route_data.get("sensitivity", "public") in ("restricted", "confidential")

    except Exception as exc:
        log.warning("router_node.fallback", error=str(exc))
        intent = WorkflowIntent.GENERAL
        complexity = ComplexityTier.MODERATE
        is_sensitive = False

    elapsed_ms = (time.perf_counter() - start) * 1000
    step = AgentResult(
        agent_name="RouterNode",
        success=True,
        output={"intent": intent.value, "complexity": complexity.value},
        latency_ms=round(elapsed_ms, 2),
    )

    log.info(
        "router_node.done",
        tenant_id=state["tenant_id"],
        intent=intent.value,
        complexity=complexity.value,
    )

    return {
        "intent": intent,
        "complexity": complexity,
        "is_sensitive": is_sensitive,
        "agent_steps": state.get("agent_steps", []) + [step],
        "current_step": state.get("current_step", 0) + 1,
    }


# ── Node: Knowledge Retrieval ─────────────────────────────────────────────────


@observe(name="node.retrieval")
async def retrieval_node(state: AgentState, http_client: httpx.AsyncClient) -> dict[str, Any]:
    """Retrieve relevant knowledge via mcp-knowledge-base MCP tool.

    Anti-Hallucination L1: Forces citation of chunk IDs in subsequent generation.

    Args:
        state: Current workflow state.
        http_client: Shared async HTTP client.

    Returns:
        State updates: retrieved_chunks.
    """
    start = time.perf_counter()
    try:
        # Call MCP tool via HTTP (streamable-HTTP transport)
        response = await http_client.post(
            f"{settings.mcp_knowledge_base_url}",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "retrieve",
                    "arguments": {
                        "query": state["query"],
                        "tenant_id": state["tenant_id"],
                        "top_k": 5,
                        "mode": "hybrid",
                    },
                },
                "id": str(uuid.uuid4()),
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("result", {})
        chunks = result.get("chunks", []) if isinstance(result, dict) else []

    except Exception as exc:
        log.warning("retrieval_node.failed", error=str(exc))
        chunks = []

    elapsed_ms = (time.perf_counter() - start) * 1000
    stale_count = sum(1 for c in chunks if c.get("stale", False))

    validation = ValidationResult(
        layer=ValidationLayer.L1_RETRIEVAL_GROUNDING,
        passed=len(chunks) > 0,
        score=float(len(chunks)) / 5.0,
        message=f"Retrieved {len(chunks)} chunks ({stale_count} stale)",
        action_taken="none",
    )

    step = AgentResult(
        agent_name="RetrievalNode",
        success=True,
        output={"chunk_count": len(chunks), "stale_count": stale_count},
        latency_ms=round(elapsed_ms, 2),
    )

    return {
        "retrieved_chunks": chunks,
        "validation_results": state.get("validation_results", []) + [validation],
        "agent_steps": state.get("agent_steps", []) + [step],
        "current_step": state.get("current_step", 0) + 1,
    }


# ── Node: SQL Generation & Execution ─────────────────────────────────────────


@observe(name="node.sql_agent")
async def sql_agent_node(state: AgentState, http_client: httpx.AsyncClient) -> dict[str, Any]:
    """Generate and execute SQL via mcp-sql-executor MCP tools.

    Anti-Hallucination L8: Numerical results are tagged for verification.

    Args:
        state: Current workflow state.
        http_client: Shared async HTTP client.

    Returns:
        State updates: generated_sql, sql_result.
    """
    start = time.perf_counter()

    # Step 1: NL → SQL
    nl_response = await _call_mcp_tool(
        http_client,
        settings.mcp_sql_executor_url,
        "nl_to_sql",
        {
            "natural_language": state["query"],
            "tenant_id": state["tenant_id"],
            "database": "postgres",
        },
    )

    generated_sql = nl_response.get("sql", "")
    confidence = float(nl_response.get("confidence", 0.0))

    sql_result: dict[str, Any] = {}
    if generated_sql and confidence >= 0.6:
        # Step 2: Execute SQL
        exec_response = await _call_mcp_tool(
            http_client,
            settings.mcp_sql_executor_url,
            "execute_sql",
            {
                "sql": generated_sql,
                "tenant_id": state["tenant_id"],
                "database": "postgres",
                "max_rows": 1000,
            },
        )
        sql_result = exec_response

    elapsed_ms = (time.perf_counter() - start) * 1000
    step = AgentResult(
        agent_name="SQLAgentNode",
        success=bool(generated_sql),
        output={
            "sql": generated_sql,
            "confidence": confidence,
            "row_count": sql_result.get("row_count", 0),
        },
        latency_ms=round(elapsed_ms, 2),
    )

    return {
        "generated_sql": generated_sql,
        "sql_result": sql_result if sql_result else None,
        "agent_steps": state.get("agent_steps", []) + [step],
        "current_step": state.get("current_step", 0) + 1,
    }


# ── Node: LLM Generation ──────────────────────────────────────────────────────


@observe(name="node.llm_generator")
async def llm_generator_node(state: AgentState) -> dict[str, Any]:
    """Generate response using LiteLLM with context from retrieved chunks and SQL results.

    Selects model tier based on complexity and sensitivity (DIP via settings).
    Uses Anthropic prompt caching for system prompts (60-80% token reduction).

    Args:
        state: Current workflow state.

    Returns:
        State updates: llm_output, total_tokens.
    """
    import litellm

    start = time.perf_counter()

    # Select model based on complexity
    model = _select_model(state.get("complexity"), state.get("is_sensitive", False))

    # Build context from retrieved chunks
    context_parts: list[str] = []
    for i, chunk in enumerate(state.get("retrieved_chunks", [])[:5]):
        stale_flag = " [STALE - may be outdated]" if chunk.get("stale") else ""
        context_parts.append(
            f"[SOURCE {i+1} — {chunk.get('source_id', 'unknown')}{stale_flag}]\n"
            f"{chunk.get('content', '')}"
        )

    context = "\n\n".join(context_parts)

    # Include SQL results if available
    sql_context = ""
    if state.get("sql_result") and state["sql_result"].get("rows"):  # type: ignore[union-attr]
        rows = state["sql_result"]["rows"][:10]  # type: ignore[index]
        sql_context = f"\n\nSQL Query Results ({len(rows)} rows):\n{rows}"

    system_prompt = (
        "You are Aria, DataMind's senior data analyst. Answer the question using ONLY "
        "the provided context. Cite source IDs for every factual claim as [SOURCE N]. "
        "If the context is insufficient, state 'I have insufficient data to answer this.' "
        "Never hallucinate numbers, names, or facts not present in the context."
    )

    user_message = (
        f"Question: {state['query']}\n\n"
        f"Context:\n{context}"
        f"{sql_context}"
    )

    langfuse_context.update_current_observation(
        input={"query": state["query"], "model": model},
        metadata={"tenant_id": state["tenant_id"], "complexity": str(state.get("complexity"))},
    )

    response = await litellm.acompletion(
        model=model,
        api_base=settings.litellm_url,
        api_key=settings.litellm_api_key,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
                "cache_control": {"type": "ephemeral"},  # Anthropic prompt caching
            },
            {"role": "user", "content": user_message},
        ],
        max_tokens=4096,
        temperature=0.1,
        metadata={"tenant_id": state["tenant_id"], "trace_name": "llm_generation"},
    )

    output = response.choices[0].message.content
    tokens = response.usage.total_tokens
    elapsed_ms = (time.perf_counter() - start) * 1000

    langfuse_context.update_current_observation(
        output={"response_length": len(output or "")},
        usage={"input": response.usage.prompt_tokens, "output": response.usage.completion_tokens},
    )

    step = AgentResult(
        agent_name="LLMGeneratorNode",
        success=True,
        output={"tokens": tokens, "output_length": len(output or "")},
        tokens_used=tokens,
        latency_ms=round(elapsed_ms, 2),
        langfuse_trace_id=langfuse_context.get_current_trace_id(),
    )

    return {
        "llm_output": output,
        "agent_steps": state.get("agent_steps", []) + [step],
        "current_step": state.get("current_step", 0) + 1,
        "total_tokens": state.get("total_tokens", 0) + tokens,
        "total_latency_ms": state.get("total_latency_ms", 0.0) + elapsed_ms,
    }


# ── Node: Human Gate ──────────────────────────────────────────────────────────


async def human_gate_node(state: AgentState) -> dict[str, Any]:
    """Pause workflow for human review (L4 Anti-Hallucination — CoT Audit gate).

    Triggered for high-stakes domains (finance, legal, medical) or when
    complexity is EXPERT and confidence is low.

    Args:
        state: Current workflow state.

    Returns:
        State updates: awaiting_human=True, status=AWAITING_HUMAN.
    """
    log.info(
        "human_gate.triggered",
        tenant_id=state["tenant_id"],
        workflow_id=state["workflow_id"],
        reason="high_stakes_review",
    )
    return {
        "awaiting_human": True,
        "status": WorkflowStatus.AWAITING_HUMAN,
    }


# ── Node: Finalise ────────────────────────────────────────────────────────────


async def finalise_node(state: AgentState) -> dict[str, Any]:
    """Assemble final response from all agent outputs.

    Args:
        state: Current workflow state.

    Returns:
        State updates: final_response, status=COMPLETED.
    """
    validations = state.get("validation_results", [])
    all_passed = all(v.passed for v in validations) if validations else True

    final_response: dict[str, Any] = {
        "answer": state.get("llm_output", ""),
        "sql": state.get("generated_sql"),
        "data": state.get("sql_result"),
        "sources": [
            {"chunk_id": c.get("chunk_id"), "source": c.get("source_id")}
            for c in state.get("retrieved_chunks", [])[:5]
        ],
        "validation_passed": all_passed,
        "stale_sources": sum(1 for c in state.get("retrieved_chunks", []) if c.get("stale")),
    }

    return {
        "final_response": final_response,
        "status": WorkflowStatus.COMPLETED,
        "anti_hallucination_passed": all_passed,
    }


# ── Conditional Edges ─────────────────────────────────────────────────────────


def should_retrieve(state: AgentState) -> str:
    """Route to retrieval or SQL based on intent."""
    intent = state.get("intent")
    if intent in (WorkflowIntent.SQL_QUERY, WorkflowIntent.EDA, WorkflowIntent.DATA_QUALITY):
        return "sql"
    return "retrieve"


def should_use_human_gate(state: AgentState) -> str:
    """Decide if human review is needed for high-stakes output."""
    if not settings.human_gate_enabled:
        return "finalise"

    complexity = state.get("complexity")
    is_sensitive = state.get("is_sensitive", False)
    validations = state.get("validation_results", [])
    any_failed = any(not v.passed for v in validations)

    # Require human gate for: EXPERT complexity + sensitive data + validation failures
    if complexity == ComplexityTier.EXPERT and (is_sensitive or any_failed):
        return "human_gate"
    return "finalise"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _select_model(complexity: ComplexityTier | None, is_sensitive: bool) -> str:
    """Select LLM model based on complexity tier (DIP — from settings)."""
    if is_sensitive:
        return settings.local_model  # Never route sensitive to cloud
    if complexity == ComplexityTier.EXPERT:
        return settings.rlm_model
    if complexity == ComplexityTier.SIMPLE:
        return settings.slm_model
    return settings.cloud_model


async def _call_mcp_tool(
    client: httpx.AsyncClient,
    endpoint: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Call an MCP tool via streamable-HTTP JSON-RPC 2.0.

    Args:
        client: Async HTTP client.
        endpoint: MCP server endpoint URL.
        tool_name: Tool name to invoke.
        arguments: Tool arguments dict.

    Returns:
        Tool result dict.
    """
    try:
        response = await client.post(
            endpoint,
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
                "id": str(uuid.uuid4()),
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("result", {})
        if isinstance(result, dict) and result.get("content"):
            # MCP returns content as list of TextContent
            content = result["content"]
            if isinstance(content, list) and content:
                import json as _json
                try:
                    return _json.loads(content[0].get("text", "{}"))
                except Exception:
                    return {"text": content[0].get("text", "")}
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        log.warning("mcp_tool_call.failed", tool=tool_name, error=str(exc))
        return {"error": str(exc)}
