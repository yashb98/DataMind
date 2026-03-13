"""
Causal Inference Router — DoWhy + EconML causal analysis endpoint.
Day 18: Phase 4 — REST API for causal effect estimation.

Protocols: None
SOLID: SRP (HTTP routing only), DIP (CausalAnalyst injected at module level)
"""
from __future__ import annotations

from fastapi import APIRouter

from ds_workbench.models import CausalAnalysisRequest, CausalAnalysisResponse
from ds_workbench.ml.causal_analyst import CausalAnalyst

router = APIRouter(prefix="/api/causal", tags=["Causal Inference"])
_analyst = CausalAnalyst()


@router.post("/analyze", response_model=CausalAnalysisResponse)
async def analyze_causal(body: CausalAnalysisRequest) -> CausalAnalysisResponse:
    """Run causal inference analysis on the provided dataset.

    Supports DoWhy (backdoor/frontdoor/IV) and EconML (DML/DR-Learner) methods.
    When use_llm_reasoning=True (default), calls DeepSeek-R1:32b for CoT interpretation.
    Falls back to naive diff-in-means if causal libraries are unavailable.

    Args:
        body: CausalAnalysisRequest with data, treatment/outcome columns, method.

    Returns:
        CausalAnalysisResponse with ATE, confidence intervals, p-value, and reasoning.
    """
    return await _analyst.analyze(body)
