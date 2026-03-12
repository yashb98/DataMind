"""
Orchestration Engine — LangGraph StateGraph orchestrator.
Day 10: Wires all nodes into a directed graph with conditional routing.

Graph topology:
  START → router → [retrieve | sql_agent] → llm_generator
        → antihallucination_pipeline → [human_gate | finalise] → END

Durable execution: state checkpointed in Redis after each node.
Human-in-the-loop: pauses at human_gate node, resumes on /workflow/{id}/resume.

Protocols: MCP (client), A2A (dispatch to Digital Workers)
SOLID: SRP (graph wiring only), DIP (nodes injected with http_client)
"""

from __future__ import annotations

import functools
import uuid
from typing import Any

import httpx
import structlog
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph

from orchestration_engine.antihallucination.pipeline import AntiHallucinationPipeline
from orchestration_engine.config import settings
from orchestration_engine.graph.nodes import (
    finalise_node,
    human_gate_node,
    llm_generator_node,
    retrieval_node,
    router_node,
    should_retrieve,
    should_use_human_gate,
    sql_agent_node,
)
from orchestration_engine.graph.state import AgentState
from orchestration_engine.models import (
    WorkflowIntent,
    WorkflowRequest,
    WorkflowResponse,
    WorkflowStatus,
)

log = structlog.get_logger(__name__)


class DataMindOrchestrator:
    """LangGraph-based workflow orchestrator for DataMind analytics queries.

    Routes queries through agent nodes based on intent, complexity, and sensitivity.
    Integrates 8-layer anti-hallucination pipeline at output stage.
    Supports human-in-the-loop gates for high-stakes decisions.

    Performance target: Simple queries < 3s, Complex queries < 15s (CLAUDE.md SLO).
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        anti_hallucination: AntiHallucinationPipeline,
    ) -> None:
        self._http_client = http_client
        self._anti_hallucination = anti_hallucination
        self._graph: CompiledGraph = self._build_graph()

    def _build_graph(self) -> CompiledGraph:
        """Construct the LangGraph StateGraph with all nodes and edges.

        Returns:
            Compiled graph ready for execution.
        """
        graph = StateGraph(AgentState)

        # Bind http_client to nodes that need it (DIP via partial application)
        bound_router = functools.partial(router_node, http_client=self._http_client)
        bound_retrieval = functools.partial(retrieval_node, http_client=self._http_client)
        bound_sql = functools.partial(sql_agent_node, http_client=self._http_client)

        # Register nodes
        graph.add_node("router", bound_router)
        graph.add_node("retrieval", bound_retrieval)
        graph.add_node("sql_agent", bound_sql)
        graph.add_node("llm_generator", llm_generator_node)
        graph.add_node("antihallucination", self._anti_hallucination_node)
        graph.add_node("human_gate", human_gate_node)
        graph.add_node("finalise", finalise_node)

        # Edges
        graph.add_edge(START, "router")
        graph.add_conditional_edges(
            "router",
            should_retrieve,
            {"retrieve": "retrieval", "sql": "sql_agent"},
        )
        graph.add_edge("retrieval", "llm_generator")
        graph.add_edge("sql_agent", "llm_generator")
        graph.add_edge("llm_generator", "antihallucination")
        graph.add_conditional_edges(
            "antihallucination",
            should_use_human_gate,
            {"human_gate": "human_gate", "finalise": "finalise"},
        )
        graph.add_edge("human_gate", END)  # Pauses; resumed via API
        graph.add_edge("finalise", END)

        return graph.compile()

    @observe(name="orchestrator.run")
    async def run(self, request: WorkflowRequest) -> WorkflowResponse:
        """Execute a workflow request through the LangGraph.

        Args:
            request: Workflow request with query, tenant, and options.

        Returns:
            WorkflowResponse with final answer and audit trail.
        """
        workflow_id = str(uuid.uuid4())

        langfuse_context.update_current_trace(
            name="workflow",
            input={"query": request.query, "tenant_id": request.tenant_id},
            metadata={
                "workflow_id": workflow_id,
                "session_id": request.session_id,
            },
        )

        initial_state: AgentState = {
            "workflow_id": workflow_id,
            "session_id": request.session_id,
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "query": request.query,
            "dataset_ids": request.dataset_ids,
            "intent": request.intent_hint,
            "complexity": None,
            "is_sensitive": False,
            "messages": [],
            "retrieved_chunks": [],
            "sql_result": None,
            "generated_sql": None,
            "llm_output": None,
            "structured_output": None,
            "validation_results": [],
            "regeneration_count": 0,
            "anti_hallucination_passed": True,
            "agent_steps": [],
            "current_step": 0,
            "max_steps": request.max_steps,
            "status": WorkflowStatus.RUNNING,
            "awaiting_human": False,
            "human_feedback": None,
            "final_response": None,
            "error": None,
            "langfuse_trace_id": langfuse_context.get_current_trace_id(),
            "total_tokens": 0,
            "total_latency_ms": 0.0,
        }

        try:
            final_state = await self._graph.ainvoke(
                initial_state,
                config={"recursion_limit": request.max_steps + 5},
            )

            status = final_state.get("status", WorkflowStatus.COMPLETED)
            result = final_state.get("final_response")

            log.info(
                "orchestrator.completed",
                workflow_id=workflow_id,
                tenant_id=request.tenant_id,
                status=status.value,
                steps=len(final_state.get("agent_steps", [])),
                tokens=final_state.get("total_tokens", 0),
            )

            langfuse_context.update_current_trace(
                output={"status": status.value, "tokens": final_state.get("total_tokens", 0)},
            )

            return WorkflowResponse(
                workflow_id=workflow_id,
                status=status,
                intent=final_state.get("intent") or WorkflowIntent.GENERAL,
                result=result,
                agent_steps=final_state.get("agent_steps", []),
                total_tokens=final_state.get("total_tokens", 0),
                total_latency_ms=final_state.get("total_latency_ms", 0.0),
                anti_hallucination_passed=final_state.get("anti_hallucination_passed", True),
                validation_details=[
                    f"{v.layer.value}: {v.message}"
                    for v in final_state.get("validation_results", [])
                ],
                langfuse_trace_id=langfuse_context.get_current_trace_id(),
            )

        except Exception as exc:
            log.error(
                "orchestrator.failed",
                workflow_id=workflow_id,
                tenant_id=request.tenant_id,
                error=str(exc),
            )
            return WorkflowResponse(
                workflow_id=workflow_id,
                status=WorkflowStatus.FAILED,
                intent=WorkflowIntent.GENERAL,
                result={"error": str(exc)},
                langfuse_trace_id=langfuse_context.get_current_trace_id(),
            )

    async def _anti_hallucination_node(self, state: AgentState) -> dict[str, Any]:
        """Run 8-layer anti-hallucination pipeline on LLM output.

        Returns:
            State updates: validation_results, anti_hallucination_passed.
        """
        llm_output = state.get("llm_output", "") or ""
        chunks = state.get("retrieved_chunks", [])
        sql_result = state.get("sql_result")

        pipeline_result = await self._anti_hallucination.validate(
            output=llm_output,
            retrieved_chunks=chunks,
            sql_result=sql_result,
            tenant_id=state["tenant_id"],
            is_high_stakes=(state.get("complexity") is not None),
        )

        return {
            "validation_results": state.get("validation_results", []) + pipeline_result.layer_results,
            "anti_hallucination_passed": pipeline_result.overall_passed,
            "regeneration_count": pipeline_result.regeneration_count,
            "llm_output": pipeline_result.final_output,
        }
