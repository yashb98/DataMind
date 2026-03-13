"""
AutoML Router — AutoGluon training, leaderboard, and inference endpoints.
Day 18: Phase 4 — REST API for automated machine learning.

Protocols: None
SOLID: SRP (HTTP routing only), DIP (AutoGluonTrainer injected at module level)
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ds_workbench.models import AutoMLPredictRequest, AutoMLPredictResponse, AutoMLTrainRequest
from ds_workbench.ml.trainer import AutoGluonTrainer

router = APIRouter(prefix="/api/automl", tags=["AutoML"])
_trainer = AutoGluonTrainer()


@router.post("/train")
async def train(body: AutoMLTrainRequest, background_tasks: BackgroundTasks) -> dict:
    """Start an AutoGluon training job as a background task.

    Args:
        body: AutoMLTrainRequest with dataset, target column, problem type, etc.
        background_tasks: FastAPI background task runner.

    Returns:
        Dict with job_id, status "started", and estimated_completion_s.
    """
    job_id = f"automl-{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(_trainer.train, body, job_id)
    return {
        "job_id": job_id,
        "status": "started",
        "estimated_completion_s": body.time_limit_s + 30,
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Poll the status of an AutoML training job.

    Args:
        job_id: Job identifier returned by /train.

    Returns:
        AutoMLJobStatus dict.

    Raises:
        HTTPException 404: If job not found.
    """
    job = _trainer.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.model_dump()


@router.get("/leaderboard/{job_id}")
async def leaderboard(job_id: str) -> dict:
    """Get the model leaderboard for a completed AutoML job.

    Args:
        job_id: Job identifier.

    Returns:
        Dict with job_id, leaderboard list, and best_model name.

    Raises:
        HTTPException 404: If job not found.
    """
    job = _trainer.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {
        "job_id": job_id,
        "leaderboard": job.leaderboard,
        "best_model": job.best_model,
    }


@router.post("/predict/{job_id}", response_model=AutoMLPredictResponse)
async def predict(job_id: str, body: AutoMLPredictRequest) -> AutoMLPredictResponse:
    """Run inference using a completed AutoML job's best model.

    Args:
        job_id: Completed job identifier.
        body: AutoMLPredictRequest with data rows and tenant_id.

    Returns:
        AutoMLPredictResponse with predictions, model name, and latency.

    Raises:
        HTTPException 404: If job not found.
        HTTPException 400: If job is not in "completed" state.
    """
    start = time.perf_counter()
    job = _trainer.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is not completed (status: {job.status})",
        )
    predictions = _trainer.predict(job_id, body.data)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return AutoMLPredictResponse(
        predictions=predictions,
        model_used=job.best_model,
        inference_ms=round(elapsed_ms, 2),
        job_id=job_id,
    )
