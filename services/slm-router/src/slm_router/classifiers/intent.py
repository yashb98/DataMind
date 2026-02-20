"""
Intent Classifier — OCP compliant: extend by adding prompt variants,
not by modifying the classifier class.

Uses Phi-3.5-mini via Ollama with a structured JSON prompt.
Falls back to rule-based classification if SLM is unavailable.
"""
import json
import re
from typing import Protocol, runtime_checkable

import httpx
import structlog

from slm_router.models import IntentLabel

log = structlog.get_logger(__name__)

# ---- Interface (OCP + DIP) -------------------------------------------------
@runtime_checkable
class IntentClassifierProtocol(Protocol):
    async def classify(self, query: str) -> tuple[IntentLabel, float]:
        """Returns (intent_label, confidence_score)."""
        ...


# ---- System prompt -----------------------------------
_INTENT_SYSTEM_PROMPT = """\
You are a query intent classifier for a data analytics platform.
Classify the user query into exactly ONE of these intent categories:

EDA       - exploratory data analysis, statistics, profiling, distributions
SQL       - requesting specific SQL queries or database lookups
FORECAST  - time-series prediction, trends, future values
ANOMALY   - outlier detection, unusual patterns, alerts
REPORT    - generate a report, summary, document, presentation
VISUALISE - create a chart, graph, plot, visualisation
CLEAN     - data cleaning, fixing errors, deduplication, imputation
MODEL     - machine learning, training a model, AutoML, feature engineering
EXPLAIN   - explain a concept, method, result, or code
SEARCH    - search knowledge base, find documents, semantic search
CODE      - write, review, debug, or explain code
GENERAL   - general question, greeting, or unclear intent

Respond ONLY with valid JSON:
{"intent": "<LABEL>", "confidence": <0.0-1.0>, "reasoning": "<1 sentence>"}
"""

# ---- Rule-based fallback (zero dependencies) -------------------------------
_KEYWORD_RULES: list[tuple[list[str], IntentLabel]] = [
    (["forecast", "predict", "future", "trend", "arima", "prophet"], IntentLabel.FORECAST),
    (["anomaly", "outlier", "unusual", "spike", "alert", "drift"],   IntentLabel.ANOMALY),
    (["report", "summary", "document", "presentation", "pptx"],      IntentLabel.REPORT),
    (["chart", "plot", "graph", "visualis", "dashboard", "bar chart", "pie"], IntentLabel.VISUALISE),
    (["clean", "deduplic", "missing", "null", "impute", "fix"],       IntentLabel.CLEAN),
    (["train", "model", "automl", "feature", "sklearn", "xgboost"],   IntentLabel.MODEL),
    (["explain", "what is", "how does", "why"],                        IntentLabel.EXPLAIN),
    (["search", "find documents", "knowledge base", "rag"],           IntentLabel.SEARCH),
    (["sql", "query", "select", "join", "where", "group by"],         IntentLabel.SQL),
    (["eda", "profile", "distribution", "statistics", "describe"],    IntentLabel.EDA),
    (["code", "python", "function", "script", "debug"],               IntentLabel.CODE),
]


def _rule_based_classify(query: str) -> tuple[IntentLabel, float]:
    q = query.lower()
    for keywords, label in _KEYWORD_RULES:
        if any(kw in q for kw in keywords):
            return label, 0.70  # Rule-based confidence = 0.70
    return IntentLabel.GENERAL, 0.60


# ---- Phi-3.5-mini Classifier -----------------------------------------------
class OllamaIntentClassifier:
    """
    SRP: Only classifies intent.
    OCP: Prompt can be swapped via Langfuse prompt versioning.
    """

    def __init__(self, ollama_url: str, model: str, timeout_s: int) -> None:
        self._url = ollama_url
        self._model = model
        self._timeout = timeout_s

    async def classify(self, query: str) -> tuple[IntentLabel, float]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._url}/api/chat",
                    json={
                        "model": self._model,
                        "stream": False,
                        "options": {"temperature": 0.0, "num_predict": 128},
                        "messages": [
                            {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                            {"role": "user", "content": f"Query: {query[:2000]}"},
                        ],
                    },
                )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()

            # Extract JSON from response (may contain markdown fence)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                raise ValueError(f"No JSON in response: {content[:200]}")

            data = json.loads(json_match.group())
            label = IntentLabel(data["intent"].upper())
            confidence = float(data.get("confidence", 0.75))
            return label, min(max(confidence, 0.0), 1.0)

        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as e:
            log.warning("intent_classifier.slm_failed", error=str(e), fallback="rule_based")
            return _rule_based_classify(query)
