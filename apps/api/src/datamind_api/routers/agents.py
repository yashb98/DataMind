"""
Agents router — Day 1 skeleton.
Full implementation: Day 8-14 (EPIC 2).
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class AgentQueryRequest(BaseModel):
    query: str
    tenant_id: str
    intent: str | None = None
    dataset_id: str | None = None


@router.post("/query")
async def agent_query(req: AgentQueryRequest):
    """
    Submit a natural language query to the agent orchestration layer.
    Routes via SLM Router → LangGraph Orchestrator → appropriate agent team.
    Full implementation: Day 8 (EPIC 2).
    """
    # Day 1 stub — returns placeholder
    return {
        "status": "stub",
        "message": "Agent orchestration not yet implemented (Day 8)",
        "query": req.query,
    }


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a running agent task."""
    return {"task_id": task_id, "status": "pending"}
