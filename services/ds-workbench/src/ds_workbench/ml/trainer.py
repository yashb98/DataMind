"""
AutoML Trainer — AutoGluon 1.2+ tabular training with MLflow tracking.
Day 18: Phase 4 — AutoML training backbone.

Protocols: None
SOLID: SRP (training only), OCP (IModelTrainer ABC), DIP (injected settings)
Benchmark: tests/benchmarks/bench_automl.py — train < 5min on <10k rows
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any

import mlflow
import pandas as pd
import structlog

from ds_workbench.config import settings
from ds_workbench.models import AutoMLJobStatus

log = structlog.get_logger(__name__)

# In-memory job store (replace with Redis in production for multi-replica)
_jobs: dict[str, AutoMLJobStatus] = {}
_predictors: dict[str, Any] = {}  # job_id → AutoGluon TabularPredictor


class IModelTrainer(ABC):
    """SOLID ISP: minimal interface for model trainers."""

    @abstractmethod
    async def train(self, request: Any, job_id: str) -> None:
        """Start async training job."""
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> AutoMLJobStatus | None:
        """Return current job status or None if not found."""
        ...

    @abstractmethod
    def predict(self, job_id: str, data: list[dict[str, Any]]) -> list[Any]:
        """Run inference on a completed job's predictor."""
        ...


class AutoGluonTrainer(IModelTrainer):
    """AutoGluon 1.2+ tabular predictor trainer with MLflow integration."""

    async def train(self, request: Any, job_id: str) -> None:
        """Run AutoGluon training in a thread pool (CPU-bound).

        Args:
            request: AutoMLTrainRequest with dataset, target_col, problem_type, etc.
            job_id: Unique job identifier — populates _jobs[job_id] on completion.
        """
        _jobs[job_id] = AutoMLJobStatus(
            job_id=job_id,
            tenant_id=request.tenant_id,
            status="running",
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._train_sync, request, job_id)

    def _train_sync(self, request: Any, job_id: str) -> None:
        """Synchronous AutoGluon training — runs in thread pool.

        Args:
            request: AutoMLTrainRequest.
            job_id: Job identifier for state storage.
        """
        start = time.perf_counter()
        try:
            from autogluon.tabular import TabularPredictor
        except ImportError:
            _jobs[job_id] = _jobs[job_id].model_copy(
                update={
                    "status": "failed",
                    "error": "AutoGluon not installed. Install autogluon.tabular.",
                }
            )
            return

        try:
            df = pd.DataFrame(request.dataset)
            if request.feature_cols:
                feature_cols = [c for c in request.feature_cols if c in df.columns]
                df = df[feature_cols + [request.target_col]]

            # MLflow experiment tracking
            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow.set_experiment(f"{settings.mlflow_experiment_name}-{request.tenant_id}")

            with mlflow.start_run(run_name=f"automl-{job_id}"):
                mlflow.log_params(
                    {
                        "problem_type": request.problem_type,
                        "presets": request.presets,
                        "time_limit_s": request.time_limit_s,
                        "n_rows": len(df),
                        "n_features": len(df.columns) - 1,
                        "target_col": request.target_col,
                        "tenant_id": request.tenant_id,
                    }
                )

                with tempfile.TemporaryDirectory() as tmpdir:
                    predictor = TabularPredictor(
                        label=request.target_col,
                        problem_type=request.problem_type,
                        eval_metric=request.eval_metric,
                        path=os.path.join(tmpdir, job_id),
                    ).fit(
                        train_data=df,
                        presets=request.presets,
                        time_limit=request.time_limit_s,
                        verbosity=0,
                    )

                    leaderboard = predictor.leaderboard(silent=True)
                    best_model = predictor.get_model_best()
                    metrics: dict[str, float] = {
                        "score_val": float(leaderboard.iloc[0].get("score_val", 0.0)),
                        "fit_time": float(leaderboard.iloc[0].get("fit_time", 0.0)),
                    }

                    mlflow.log_metrics(metrics)
                    mlflow.log_param("best_model", best_model)

                    # Store predictor in memory for predictions
                    _predictors[job_id] = predictor

                    elapsed_ms = (time.perf_counter() - start) * 1000
                    _jobs[job_id] = _jobs[job_id].model_copy(
                        update={
                            "status": "completed",
                            "leaderboard": leaderboard[
                                ["model", "score_val", "fit_time"]
                            ]
                            .head(10)
                            .to_dict("records"),
                            "best_model": best_model,
                            "metrics": metrics,
                            "training_ms": round(elapsed_ms, 2),
                            "completed_at": _now_iso(),
                        }
                    )
                    log.info(
                        "automl.train.done",
                        job_id=job_id,
                        best_model=best_model,
                        elapsed_ms=elapsed_ms,
                    )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.error("automl.train.failed", job_id=job_id, error=str(exc))
            _jobs[job_id] = _jobs[job_id].model_copy(
                update={
                    "status": "failed",
                    "error": str(exc),
                    "training_ms": round(elapsed_ms, 2),
                }
            )

    def get_job(self, job_id: str) -> AutoMLJobStatus | None:
        """Return job status.

        Args:
            job_id: Job identifier.

        Returns:
            AutoMLJobStatus or None if job not found.
        """
        return _jobs.get(job_id)

    def predict(self, job_id: str, data: list[dict[str, Any]]) -> list[Any]:
        """Run inference using the trained predictor.

        Args:
            job_id: Completed job identifier.
            data: List of row dicts for inference.

        Returns:
            List of predictions.

        Raises:
            ValueError: If no predictor exists for this job_id.
        """
        predictor = _predictors.get(job_id)
        if predictor is None:
            raise ValueError(f"No predictor found for job {job_id}")
        df = pd.DataFrame(data)
        preds = predictor.predict(df)
        return preds.tolist()


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
