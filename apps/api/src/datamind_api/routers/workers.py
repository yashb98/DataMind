"""
Digital Workers router — Day 1 skeleton.
Full implementation: Day 26 (EPIC 7).
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class WorkerDeployRequest(BaseModel):
    template_name: str  # aria | max | luna | atlas | nova | sage | echo | iris | rex | geo | swift | quant
    tenant_id: str
    customisations: dict | None = None


@router.post("/deploy")
async def deploy_worker(req: WorkerDeployRequest):
    """
    Deploy a Digital Worker from a template.
    Full implementation: Day 26.
    """
    return {
        "status": "stub",
        "message": "Worker deployment not yet implemented (Day 26)",
        "template": req.template_name,
    }


@router.get("/")
async def list_workers(tenant_id: str):
    """List all Digital Workers for a tenant."""
    return {"workers": [], "total": 0}


@router.post("/kill-switch")
async def kill_switch(tenant_id: str):
    """
    Emergency stop — pause all workers for a tenant.
    Returns within 10 seconds with all workers in PAUSED state.
    Full implementation: Day 26.
    """
    return {"status": "stub", "message": "Kill switch not yet implemented (Day 26)"}
