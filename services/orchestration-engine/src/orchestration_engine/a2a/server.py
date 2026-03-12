"""
Orchestration Engine — A2A Protocol Server (Google A2A v0.3).
Day 10: Exposes tasks/send, tasks/get, tasks/sendSubscribe (SSE) endpoints.
Publishes Agent Card at /.well-known/agent.json.

A2A Task Lifecycle:
  submitted → working → [input-required] → completed | failed

Protocols: A2A v0.3 (agent cards, task lifecycle, SSE streaming)
SOLID: SRP (A2A protocol only), OCP (new skill = new function, no changes here)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from orchestration_engine.models import (
    A2ASkill,
    A2ATask,
    A2ATaskResponse,
    A2ATaskState,
    AgentCard,
    A2ASendTaskRequest,
)

log = structlog.get_logger(__name__)

# ── In-memory task store (Redis-backed in production) ─────────────────────────
_tasks: dict[str, A2ATask] = {}

router = APIRouter(prefix="/a2a", tags=["A2A"])

# ── Agent Card ────────────────────────────────────────────────────────────────

_ORCHESTRATOR_CARD = AgentCard(
    name="DataMind Orchestration Engine",
    description=(
        "DataMind's central AI orchestrator. Accepts natural language analytics queries "
        "and delegates to specialised Digital Workers (Aria, Max, Luna, Atlas, etc.) "
        "via the A2A protocol. Supports SQL analysis, forecasting, reporting, compliance, "
        "and causal inference."
    ),
    url="http://orchestration-engine:8060",
    skills=[
        A2ASkill(
            id="analytics_query",
            name="Analytics Query",
            description="Answer natural language questions about your data using SQL, RAG, and ML",
            tags=["analytics", "sql", "rag", "nlp"],
            input_modes=["text"],
            output_modes=["text", "data"],
        ),
        A2ASkill(
            id="eda",
            name="Exploratory Data Analysis",
            description="Automated EDA with statistical summaries and anomaly detection",
            tags=["eda", "statistics", "anomaly"],
            input_modes=["text", "dataset_id"],
            output_modes=["text", "chart", "report"],
        ),
        A2ASkill(
            id="report_generation",
            name="Report Generation",
            description="Generate PDF/PPTX reports with Merkle provenance certificate",
            tags=["report", "pdf", "pptx", "narrative"],
            input_modes=["text", "dataset_id"],
            output_modes=["pdf", "pptx", "text"],
        ),
        A2ASkill(
            id="forecast",
            name="Time Series Forecast",
            description="Multi-horizon forecasting with Prophet, NeuralForecast, and Chronos",
            tags=["forecast", "timeseries", "prediction"],
            input_modes=["text", "dataset_id"],
            output_modes=["data", "chart"],
        ),
    ],
    authentication={"schemes": ["bearer"]},
    capabilities={
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": True,
    },
)


# ── A2A Endpoints ─────────────────────────────────────────────────────────────


@router.get("/.well-known/agent.json", include_in_schema=False)
async def get_agent_card() -> dict[str, Any]:
    """Publish Agent Card at well-known URL per A2A spec."""
    return _ORCHESTRATOR_CARD.model_dump(mode="json")


@router.post("/tasks/send", response_model=A2ATaskResponse)
async def send_task(request: A2ASendTaskRequest) -> A2ATaskResponse:
    """Submit a new A2A task and begin processing.

    Implements A2A tasks/send endpoint.
    Task moves: submitted → working → completed/failed.

    Args:
        request: A2A task send request with message payload.

    Returns:
        Task ID and initial state (submitted).
    """
    task = A2ATask(
        id=request.id,
        session_id=request.session_id,
        state=A2ATaskState.SUBMITTED,
        message=request.message,
        metadata=request.metadata,
    )
    _tasks[task.id] = task

    # Begin async processing (fire-and-forget; client polls via tasks/get)
    asyncio.create_task(_process_task(task))

    log.info("a2a.task.submitted", task_id=task.id, session_id=task.session_id)

    return A2ATaskResponse(
        id=task.id,
        session_id=task.session_id,
        state=A2ATaskState.SUBMITTED,
    )


@router.get("/tasks/{task_id}", response_model=A2ATaskResponse)
async def get_task(task_id: str) -> A2ATaskResponse:
    """Poll task state (A2A tasks/get endpoint).

    Args:
        task_id: Task identifier returned from tasks/send.

    Returns:
        Current task state and result if completed.

    Raises:
        HTTPException: 404 if task not found.
    """
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return A2ATaskResponse(
        id=task.id,
        session_id=task.session_id,
        state=task.state,
        result=task.result,
        error=task.error,
    )


@router.post("/tasks/{task_id}/subscribe")
async def subscribe_task(task_id: str) -> StreamingResponse:
    """Stream task state updates via SSE (A2A tasks/sendSubscribe endpoint).

    Args:
        task_id: Task identifier to subscribe to.

    Returns:
        SSE stream of state transition events.

    Raises:
        HTTPException: 404 if task not found.
    """
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return StreamingResponse(
        _stream_task_events(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tasks/{task_id}/human-input")
async def provide_human_input(task_id: str, feedback: dict[str, Any]) -> A2ATaskResponse:
    """Resume a paused task after human review (input-required → working).

    Args:
        task_id: Task identifier.
        feedback: Human reviewer's feedback dict.

    Returns:
        Updated task state.
    """
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.state != A2ATaskState.INPUT_REQUIRED:
        raise HTTPException(
            status_code=400,
            detail=f"Task is in state {task.state.value}, not input-required",
        )

    task.state = A2ATaskState.WORKING
    task.metadata["human_feedback"] = feedback
    asyncio.create_task(_process_task(task, resume=True))

    log.info("a2a.task.resumed", task_id=task_id)
    return A2ATaskResponse(id=task.id, session_id=task.session_id, state=task.state)


# ── Internal Processing ───────────────────────────────────────────────────────


async def _process_task(task: A2ATask, resume: bool = False) -> None:
    """Process an A2A task through the orchestration engine.

    Args:
        task: A2A task to process.
        resume: Whether this is resuming from input-required state.
    """
    task.state = A2ATaskState.WORKING
    try:
        # Import here to avoid circular imports
        from orchestration_engine.main import _orchestrator  # type: ignore[import]

        if _orchestrator is None:
            raise RuntimeError("Orchestrator not initialised")

        # Extract query and tenant from A2A message
        message = task.message
        query = _extract_text_content(message)
        tenant_id = task.metadata.get("tenant_id", "default")
        user_id = task.metadata.get("user_id", "a2a_user")

        from orchestration_engine.models import WorkflowRequest

        request = WorkflowRequest(
            query=query,
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            session_id=task.session_id,
        )

        result = await _orchestrator.run(request)
        task.state = A2ATaskState.COMPLETED
        task.result = result.model_dump(mode="json")

        log.info(
            "a2a.task.completed",
            task_id=task.id,
            workflow_id=result.workflow_id,
        )

    except Exception as exc:
        task.state = A2ATaskState.FAILED
        task.error = str(exc)
        log.error("a2a.task.failed", task_id=task.id, error=str(exc))


async def _stream_task_events(task_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE events for task state transitions.

    Args:
        task_id: Task to stream events for.

    Yields:
        SSE-formatted event strings.
    """
    last_state: A2ATaskState | None = None
    poll_count = 0
    max_polls = 600  # 5 minutes at 500ms intervals

    while poll_count < max_polls:
        task = _tasks.get(task_id)
        if task is None:
            break

        if task.state != last_state:
            last_state = task.state
            event_data = json.dumps({
                "task_id": task_id,
                "state": task.state.value,
                "result": task.result,
                "error": task.error,
            })
            yield f"data: {event_data}\n\n"

        if task.state in (A2ATaskState.COMPLETED, A2ATaskState.FAILED, A2ATaskState.INPUT_REQUIRED):
            break

        await asyncio.sleep(0.5)
        poll_count += 1

    yield "data: {\"type\": \"stream_end\"}\n\n"


def _extract_text_content(message: dict[str, Any]) -> str:
    """Extract text content from A2A message format.

    A2A message format: {"role": "user", "parts": [{"type": "text", "text": "..."}]}
    """
    parts = message.get("parts", [])
    texts = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            texts.append(part.get("text", ""))
    return " ".join(texts) or str(message.get("content", ""))
