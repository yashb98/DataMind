"""
Complexity Scorer — estimates query complexity (0.0..1.0) via Gemma-2-2B.
Higher complexity → more expensive inference tier.

Factors considered:
  - Multi-step reasoning required
  - Number of entities / conditions
  - Data volume implied
  - Temporal / causal reasoning
  - Statistical sophistication
"""
import json
import re

import httpx
import structlog

from slm_router.models import ComplexityLevel

log = structlog.get_logger(__name__)

_COMPLEXITY_SYSTEM_PROMPT = """\
You are a query complexity estimator for a data analytics AI platform.
Score the complexity of the user query from 0.0 to 1.0 based on:

- 0.0-0.35 SIMPLE: Single table lookup, basic aggregation, factual question
  Example: "Show total sales for last month"
- 0.35-0.65 MEDIUM: Multi-step analysis, comparisons, joins across 2-3 tables
  Example: "Compare revenue across regions and highlight top performers"
- 0.65-0.85 COMPLEX: Causal analysis, multi-hop reasoning, statistical tests
  Example: "What factors drove the Q3 revenue drop? Show contributing variables"
- 0.85-1.0 EXPERT: Causal inference, forecasting with confounders, hypothesis testing
  Example: "Build a causal model to estimate the impact of the price change on churn"

Respond ONLY with valid JSON:
{"score": <0.0-1.0>, "level": "<simple|medium|complex|expert>", "factors": ["factor1", "factor2"]}
"""


def _heuristic_complexity(query: str) -> tuple[float, ComplexityLevel]:
    """Zero-dependency fallback complexity estimation."""
    q = query.lower()
    score = 0.2  # baseline

    # Positive complexity signals
    complex_words = [
        "why", "cause", "because", "explain why", "reason",
        "compare", "correlation", "regression", "statistical",
        "forecast", "predict", "causal", "hypothesis",
        "multi", "across", "segment", "cohort", "attribution",
        "counterfactual", "confound", "a/b test", "significance",
    ]
    medium_words = [
        "trend", "breakdown", "by region", "by segment", "over time",
        "growth", "change", "vs", "versus", "top", "bottom", "rank",
        "percentage", "ratio", "average", "group by",
    ]

    score += sum(0.08 for w in complex_words if w in q)
    score += sum(0.04 for w in medium_words if w in q)

    # Length heuristic
    words = len(query.split())
    if words > 50:
        score += 0.1
    elif words > 25:
        score += 0.05

    score = min(score, 1.0)

    if score <= 0.35:
        return score, ComplexityLevel.SIMPLE
    elif score <= 0.65:
        return score, ComplexityLevel.MEDIUM
    elif score <= 0.85:
        return score, ComplexityLevel.COMPLEX
    return score, ComplexityLevel.EXPERT


class OllamaComplexityScorer:
    """SRP: Only scores complexity. Gemma-2-2B is small enough for < 50ms."""

    def __init__(self, ollama_url: str, model: str, timeout_s: int) -> None:
        self._url = ollama_url
        self._model = model
        self._timeout = timeout_s

    async def score(self, query: str) -> tuple[float, ComplexityLevel, float]:
        """Returns (score 0..1, level, confidence)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._url}/api/chat",
                    json={
                        "model": self._model,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 128},
                        "messages": [
                            {"role": "system", "content": _COMPLEXITY_SYSTEM_PROMPT},
                            {"role": "user", "content": f"Query: {query[:2000]}"},
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON in response")

            data = json.loads(json_match.group())
            raw_score = float(data.get("score", 0.5))
            score = min(max(raw_score, 0.0), 1.0)

            level_map = {
                "simple": ComplexityLevel.SIMPLE,
                "medium": ComplexityLevel.MEDIUM,
                "complex": ComplexityLevel.COMPLEX,
                "expert": ComplexityLevel.EXPERT,
            }
            level = level_map.get(data.get("level", "medium").lower(), ComplexityLevel.MEDIUM)
            return score, level, 0.82  # SLM confidence

        except Exception as e:
            log.warning("complexity_scorer.slm_failed", error=str(e), fallback="heuristic")
            score, level = _heuristic_complexity(query)
            return score, level, 0.65  # Heuristic confidence
