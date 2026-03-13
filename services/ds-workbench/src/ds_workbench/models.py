"""
DS Workbench Models — Pydantic request/response models for all 4 routers.
Day 18: Phase 4 — AutoML, Forecasting, Causal Inference, Model Deployment.

Protocols: None
SOLID: SRP (data shapes only)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# ── AutoML ────────────────────────────────────────────────────────────────────


class AutoMLTrainRequest(BaseModel):
    dataset: list[dict[str, Any]]
    target_col: str
    problem_type: Literal["binary", "multiclass", "regression"] = "regression"
    tenant_id: str
    user_id: str = "system"
    time_limit_s: int = 300
    feature_cols: list[str] | None = None
    presets: Literal["medium_quality", "best_quality", "optimize_for_deployment"] = "medium_quality"
    eval_metric: str | None = None


class AutoMLJobStatus(BaseModel):
    job_id: str
    tenant_id: str
    status: Literal["pending", "running", "completed", "failed"]
    leaderboard: list[dict[str, Any]] = []
    best_model: str = ""
    metrics: dict[str, float] = {}
    training_ms: float = 0.0
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None


class AutoMLTrainResponse(BaseModel):
    job_id: str
    status: Literal["started"]
    estimated_completion_s: int


class AutoMLPredictRequest(BaseModel):
    data: list[dict[str, Any]]
    tenant_id: str


class AutoMLPredictResponse(BaseModel):
    predictions: list[Any]
    model_used: str
    inference_ms: float
    job_id: str


# ── Forecasting ───────────────────────────────────────────────────────────────


class ForecastTrainRequest(BaseModel):
    data: list[dict[str, Any]]
    date_col: str
    value_col: str
    periods: int = 30
    frequency: Literal["D", "W", "M", "Q", "Y"] = "D"
    model: Literal["prophet", "nhits", "tft", "chronos", "auto"] = "auto"
    tenant_id: str
    group_cols: list[str] = []  # For hierarchical forecasting


class ForecastTrainResponse(BaseModel):
    job_id: str
    model_used: str
    status: Literal["completed", "failed"]


class ForecastPredictRequest(BaseModel):
    job_id: str
    periods: int = 30
    confidence_level: float = 0.95
    tenant_id: str


class ForecastPoint(BaseModel):
    ds: str
    yhat: float
    yhat_lower: float
    yhat_upper: float


class ForecastResponse(BaseModel):
    job_id: str
    forecast: list[ForecastPoint]
    model_used: str
    mape: float | None = None
    rmse: float | None = None
    confidence_level: float = 0.95
    generation_ms: float


# ── Causal ────────────────────────────────────────────────────────────────────


class CausalAnalysisRequest(BaseModel):
    data: list[dict[str, Any]]
    treatment_col: str
    outcome_col: str
    covariates: list[str] = []
    method: Literal["backdoor", "frontdoor", "iv", "econml_dml", "econml_drlearner"] = "backdoor"
    tenant_id: str
    user_id: str = "system"
    use_llm_reasoning: bool = True  # DeepSeek-R1 for CoT reasoning


class CausalAnalysisResponse(BaseModel):
    causal_estimate: float
    confidence_interval: tuple[float, float]
    method_used: str
    ate: float
    p_value: float | None = None
    reasoning: str  # CoT from DeepSeek-R1
    feature_importance: dict[str, float] = {}
    analysis_ms: float


# ── Deployment ────────────────────────────────────────────────────────────────


class DeployModelRequest(BaseModel):
    job_id: str
    model_name: str
    tenant_id: str
    description: str = ""


class DeployedModel(BaseModel):
    deployment_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    job_id: str
    model_name: str
    tenant_id: str
    endpoint_url: str
    status: Literal["deploying", "running", "stopped", "failed"]
    deploy_ms: float = 0.0
    description: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
