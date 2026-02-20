"""
SLM Router — core routing decision engine.

Implements the 4-tier routing logic:
  EDGE  (< 20ms)  → Cloudflare Workers AI / WebLLM
  SLM   (< 100ms) → Ollama Phi-3.5-mini / Gemma-2-2B
  CLOUD (< 1s)    → LiteLLM → Claude / GPT-4o / Gemini
  RLM   (< 5s)    → vLLM DeepSeek-R1:32b

Design: DIP — depends on classifier abstractions, not concretions.
        OCP — add new routing rules without modifying this class.
"""
import asyncio
import hashlib
import json
from typing import Any

import redis.asyncio as aioredis
import structlog
from langfuse import Langfuse

from slm_router.classifiers.complexity import OllamaComplexityScorer
from slm_router.classifiers.intent import OllamaIntentClassifier
from slm_router.classifiers.sensitivity import RuleBasedSensitivityDetector
from slm_router.config import settings
from slm_router.models import (
    ClassificationResult,
    ComplexityLevel,
    InferenceTier,
    IntentLabel,
    RouteRequest,
    RouteResponse,
    SensitivityLevel,
)

log = structlog.get_logger(__name__)


# ---- Model selection map (OCP: extend this dict, not the method) -----------
_TIER_MODELS: dict[InferenceTier, dict[IntentLabel | str, str]] = {
    InferenceTier.EDGE: {
        "default": settings.edge_model,
    },
    InferenceTier.SLM: {
        "default": settings.intent_model,
    },
    InferenceTier.CLOUD: {
        IntentLabel.SQL:      settings.cloud_sql_model,
        IntentLabel.CODE:     settings.cloud_sql_model,
        IntentLabel.MODEL:    settings.cloud_analysis_model,
        IntentLabel.EDA:      settings.cloud_analysis_model,
        "default":            settings.cloud_default_model,
    },
    InferenceTier.RLM: {
        "default": settings.rlm_model,
    },
}

_LATENCY_BUDGETS = {
    InferenceTier.EDGE:  settings.latency_edge_ms,
    InferenceTier.SLM:   settings.latency_slm_ms,
    InferenceTier.CLOUD: settings.latency_cloud_ms,
    InferenceTier.RLM:   settings.latency_rlm_ms,
}


def _select_model(tier: InferenceTier, intent: IntentLabel) -> str:
    tier_map = _TIER_MODELS[tier]
    return tier_map.get(intent, tier_map["default"])


def _determine_tier(
    complexity: ComplexityLevel,
    sensitivity: SensitivityLevel,
    intent_confidence: float,
    complexity_score: float,
) -> tuple[InferenceTier, str]:
    """
    Core routing decision tree.
    Returns (tier, routing_reason).
    """
    # Security gate: sensitive data CANNOT go to cloud/edge
    if sensitivity in (SensitivityLevel.RESTRICTED, SensitivityLevel.CONFIDENTIAL):
        if complexity == ComplexityLevel.EXPERT:
            return InferenceTier.RLM, f"RLM local (sensitivity={sensitivity.value}, complexity=expert)"
        return InferenceTier.SLM, f"Local SLM enforced (sensitivity={sensitivity.value})"

    # Low confidence on intent → escalate to cloud for safety
    if intent_confidence < settings.slm_confidence_threshold:
        return InferenceTier.CLOUD, f"Escalated: low SLM confidence ({intent_confidence:.2f})"

    # Routing by complexity
    if complexity == ComplexityLevel.SIMPLE and complexity_score <= 0.35:
        # Edge only viable for very simple queries
        return InferenceTier.EDGE, "Edge: simple query, high confidence"

    if complexity in (ComplexityLevel.SIMPLE, ComplexityLevel.MEDIUM):
        return InferenceTier.CLOUD, f"Cloud LLM: complexity={complexity.value}"

    if complexity == ComplexityLevel.COMPLEX:
        return InferenceTier.CLOUD, f"Cloud LLM: complex query (no reasoning chain needed)"

    # Expert / very high complexity → RLM
    return InferenceTier.RLM, f"RLM: expert complexity (score={complexity_score:.2f})"


class SLMRouter:
    """
    Single Responsibility: routing decisions only.
    All classification delegated to injected classifiers (DIP).
    """

    def __init__(
        self,
        intent_clf: OllamaIntentClassifier,
        complexity_scorer: OllamaComplexityScorer,
        sensitivity_detector: RuleBasedSensitivityDetector,
        redis_client: aioredis.Redis,
        langfuse: Langfuse,
    ) -> None:
        self._intent = intent_clf
        self._complexity = complexity_scorer
        self._sensitivity = sensitivity_detector
        self._redis = redis_client
        self._langfuse = langfuse

    def _cache_key(self, query: str) -> str:
        h = hashlib.sha256(query.encode()).hexdigest()[:16]
        return f"slm_router:route:{h}"

    async def _get_cached(self, key: str) -> RouteResponse | None:
        try:
            raw = await self._redis.get(key)
            if raw:
                return RouteResponse.model_validate_json(raw)
        except Exception:
            pass
        return None

    async def _set_cached(self, key: str, response: RouteResponse) -> None:
        try:
            await self._redis.setex(key, settings.cache_ttl_s, response.model_dump_json())
        except Exception:
            pass

    async def route(self, req: RouteRequest) -> RouteResponse:
        """
        Main routing entry point.
        Runs intent + complexity + sensitivity in parallel for < 100ms total.
        """
        # Honour forced tier (testing / admin override)
        if req.force_tier:
            return self._forced_response(req)

        # Cache check
        cache_key = self._cache_key(req.query)
        cached = await self._get_cached(cache_key)
        if cached:
            cached.cached = True
            return cached

        trace = self._langfuse.trace(
            name="slm_router.route",
            metadata={"tenant_id": req.tenant_id},
        )

        try:
            # Run all classifiers in parallel (DIP: inject any classifier impl)
            intent_task = self._intent.classify(req.query)
            complexity_task = self._complexity.score(req.query)
            sensitivity_result = self._sensitivity.detect(req.query)

            (intent, intent_conf), (complexity_score, complexity, complexity_conf) = \
                await asyncio.gather(intent_task, complexity_task)

            sensitivity, sensitivity_conf = sensitivity_result

            tier, reason = _determine_tier(
                complexity, sensitivity, intent_conf, complexity_score
            )
            model = _select_model(tier, intent)

            clf = ClassificationResult(
                intent=intent,
                intent_confidence=intent_conf,
                complexity=complexity,
                complexity_confidence=complexity_conf,
                sensitivity=sensitivity,
                sensitivity_confidence=sensitivity_conf,
            )

            response = RouteResponse(
                tier=tier,
                model=model,
                intent=intent,
                complexity=complexity,
                sensitivity=sensitivity,
                confidence=min(intent_conf, complexity_conf, sensitivity_conf),
                latency_budget_ms=_LATENCY_BUDGETS[tier],
                routing_reason=reason,
                classification=clf,
                cached=False,
            )

            trace.update(
                output={"tier": tier, "model": model, "intent": intent, "confidence": response.confidence}
            )

            await self._set_cached(cache_key, response)
            log.info(
                "slm_router.routed",
                tier=tier,
                model=model,
                intent=intent,
                complexity=complexity.value,
                sensitivity=sensitivity.value,
                confidence=f"{response.confidence:.2f}",
            )
            return response

        except Exception as e:
            log.error("slm_router.error", error=str(e))
            # Safe fallback: cloud LLM, general intent
            return RouteResponse(
                tier=InferenceTier.CLOUD,
                model=settings.cloud_default_model,
                intent=IntentLabel.GENERAL,
                complexity=ComplexityLevel.MEDIUM,
                sensitivity=SensitivityLevel.INTERNAL,
                confidence=0.5,
                latency_budget_ms=settings.latency_cloud_ms,
                routing_reason=f"Fallback: router error ({str(e)[:50]})",
                classification=ClassificationResult(
                    intent=IntentLabel.GENERAL, intent_confidence=0.5,
                    complexity=ComplexityLevel.MEDIUM, complexity_confidence=0.5,
                    sensitivity=SensitivityLevel.INTERNAL, sensitivity_confidence=0.5,
                ),
            )

    def _forced_response(self, req: RouteRequest) -> RouteResponse:
        tier = req.force_tier  # type: ignore[assignment]
        return RouteResponse(
            tier=tier,
            model=_select_model(tier, IntentLabel.GENERAL),
            intent=IntentLabel.GENERAL,
            complexity=ComplexityLevel.MEDIUM,
            sensitivity=SensitivityLevel.PUBLIC,
            confidence=1.0,
            latency_budget_ms=_LATENCY_BUDGETS[tier],
            routing_reason=f"Forced tier: {tier}",
            classification=ClassificationResult(
                intent=IntentLabel.GENERAL, intent_confidence=1.0,
                complexity=ComplexityLevel.MEDIUM, complexity_confidence=1.0,
                sensitivity=SensitivityLevel.PUBLIC, sensitivity_confidence=1.0,
            ),
        )
