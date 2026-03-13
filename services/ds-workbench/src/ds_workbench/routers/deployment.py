"""
Model Deployment Router — BentoML-backed model serving via REST.
Day 18: Phase 4 — Deploy trained AutoML models with CRYSTALS-Dilithium artifact signing.

Protocols: None
SOLID: SRP (HTTP routing only), DIP (signing + jobs injected)
"""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import APIRouter, HTTPException

from ds_workbench.models import DeployModelRequest, DeployedModel
from ds_workbench.ml.trainer import _jobs
from ds_workbench.ml.signing import sign_artifact

router = APIRouter(prefix="/api/models", tags=["Model Deployment"])
log = structlog.get_logger(__name__)

# In-memory deployment registry (tenant-isolated)
_deployments: dict[str, DeployedModel] = {}


@router.post("/deploy", response_model=DeployedModel)
async def deploy_model(body: DeployModelRequest) -> DeployedModel:
    """Deploy a completed AutoML model as a REST endpoint.

    Signs the artifact with CRYSTALS-Dilithium3 (or HMAC-SHA256 fallback) before
    registering the deployment. The endpoint URL points back to the predict route.

    Args:
        body: DeployModelRequest with job_id, model_name, tenant_id, description.

    Returns:
        DeployedModel with deployment_id, endpoint_url, status "running", and deploy_ms.

    Raises:
        HTTPException 400: If job is not completed or not found.
    """
    job = _jobs.get(body.job_id)
    if not job or job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job {body.job_id} not ready for deployment (status: {job.status if job else 'not found'})",
        )

    start = time.perf_counter()
    deployment_id = f"dep-{uuid.uuid4().hex[:8]}"

    # Sign the artifact with CRYSTALS-Dilithium3
    artifact: dict = {
        "deployment_id": deployment_id,
        "job_id": body.job_id,
        "model_name": body.model_name,
        "best_model": job.best_model,
        "metrics": job.metrics,
        "tenant_id": body.tenant_id,
    }
    signed = sign_artifact(artifact)
    log.info(
        "model.signed",
        deployment_id=deployment_id,
        algorithm=signed.get("algorithm"),
        artifact_hash=signed.get("artifact_hash"),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    deployment = DeployedModel(
        deployment_id=deployment_id,
        job_id=body.job_id,
        model_name=body.model_name,
        tenant_id=body.tenant_id,
        endpoint_url=f"http://ds-workbench:8120/api/automl/predict/{body.job_id}",
        status="running",
        deploy_ms=round(elapsed_ms, 2),
        description=body.description,
    )
    _deployments[deployment_id] = deployment
    log.info(
        "model.deployed",
        deployment_id=deployment_id,
        model_name=body.model_name,
        tenant_id=body.tenant_id,
        elapsed_ms=elapsed_ms,
    )
    return deployment


@router.get("", response_model=list[DeployedModel])
async def list_models(tenant_id: str) -> list[DeployedModel]:
    """List all deployed models for the given tenant.

    Args:
        tenant_id: Tenant identifier for filtering deployments.

    Returns:
        List of DeployedModel records for this tenant.
    """
    return [d for d in _deployments.values() if d.tenant_id == tenant_id]


@router.delete("/{deployment_id}")
async def delete_deployment(deployment_id: str, tenant_id: str) -> dict:
    """Stop and remove a deployed model.

    Args:
        deployment_id: Deployment identifier.
        tenant_id: Tenant identifier (must match deployment owner).

    Returns:
        Dict with status "stopped" and deployment_id.

    Raises:
        HTTPException 404: If deployment not found or tenant mismatch.
    """
    dep = _deployments.get(deployment_id)
    if not dep or dep.tenant_id != tenant_id:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment {deployment_id} not found for tenant {tenant_id}",
        )
    _deployments[deployment_id] = dep.model_copy(update={"status": "stopped"})
    log.info("model.undeployed", deployment_id=deployment_id, tenant_id=tenant_id)
    return {"status": "stopped", "deployment_id": deployment_id}
