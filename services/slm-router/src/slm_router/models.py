"""
SLM Router — Pydantic models for request/response contracts.
All types are strict (no coercion surprises).
"""
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# ---- Intent Labels --------------------------------------------------------
class IntentLabel(str, Enum):
    EDA          = "EDA"
    SQL          = "SQL"
    FORECAST     = "FORECAST"
    ANOMALY      = "ANOMALY"
    REPORT       = "REPORT"
    VISUALISE    = "VISUALISE"
    CLEAN        = "CLEAN"
    MODEL        = "MODEL"
    EXPLAIN      = "EXPLAIN"
    SEARCH       = "SEARCH"
    CODE         = "CODE"
    GENERAL      = "GENERAL"


# ---- Complexity Tiers ------------------------------------------------------
class ComplexityLevel(str, Enum):
    SIMPLE  = "simple"    # edge or local SLM sufficient
    MEDIUM  = "medium"    # standard cloud LLM
    COMPLEX = "complex"   # cloud LLM with more context
    EXPERT  = "expert"    # RLM (DeepSeek-R1 / o3-mini)


# ---- Sensitivity Levels ----------------------------------------------------
class SensitivityLevel(str, Enum):
    PUBLIC       = "public"      # safe to send to cloud LLM
    INTERNAL     = "internal"    # prefer local, ok for cloud with tenant consent
    CONFIDENTIAL = "confidential"  # local only — no cloud LLM
    RESTRICTED   = "restricted"  # PII / financial / medical — must stay local


# ---- Inference Tier --------------------------------------------------------
class InferenceTier(str, Enum):
    EDGE   = "edge"    # Cloudflare Workers AI / WebLLM — < 20ms
    SLM    = "slm"     # Ollama local SLM — < 100ms
    CLOUD  = "cloud"   # LiteLLM → cloud LLM — < 1s
    RLM    = "rlm"     # vLLM DeepSeek-R1:32b — < 5s


# ---- Request / Response ----------------------------------------------------
class RouteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=32_000)
    tenant_id: str
    context_tokens: int = Field(default=0, ge=0)
    force_tier: InferenceTier | None = None  # override for testing
    metadata: dict | None = None


class ClassificationResult(BaseModel):
    intent: IntentLabel
    intent_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    complexity: ComplexityLevel
    complexity_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    sensitivity: SensitivityLevel
    sensitivity_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str | None = None


class RouteResponse(BaseModel):
    tier: InferenceTier
    model: str                   # exact model name to use
    intent: IntentLabel
    complexity: ComplexityLevel
    sensitivity: SensitivityLevel
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    latency_budget_ms: int       # max allowed latency for downstream
    routing_reason: str
    classification: ClassificationResult
    cached: bool = False
