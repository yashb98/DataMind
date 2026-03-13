"""
RAG API — RAGAS-Style RAG Quality Evaluator.
Day 22: Phase 5 — Faithfulness, answer relevancy, context recall → MLflow.

Evaluation metrics:
  - faithfulness:       fraction of claims in answer supported by context (NLI via LLM)
  - answer_relevancy:   cosine sim(answer_embedding, question_embedding)
  - context_recall:     fraction of ground truth facts covered by context (optional)

Protocols: None
SOLID: SRP (evaluation only), DIP (http + mlflow injected)
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import mlflow
import numpy as np
import structlog
from langfuse.decorators import observe
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.models import RAGASResult

log = structlog.get_logger(__name__)

_FAITHFULNESS_SYSTEM = """You are an NLI (Natural Language Inference) evaluator.

Given an ANSWER and a list of CONTEXTS, decompose the answer into individual
factual claims, then verify each claim against the contexts.

Return JSON:
{
  "claims": ["claim 1", "claim 2", ...],
  "verdicts": [
    {"claim": "claim 1", "verdict": "supported|unsupported|unknown", "evidence": "quote from context or empty"}
  ],
  "supported_count": <int>,
  "total_count": <int>
}

Rules:
- "supported" = claim is directly entailed by or consistent with at least one context
- "unsupported" = claim contradicts contexts or has no evidence
- "unknown" = contexts don't address the claim (treat as unsupported for scoring)
- Be strict: do not give credit for vague consistency
"""

_CONTEXT_RECALL_SYSTEM = """You are a context coverage evaluator.

Given a GROUND TRUTH answer and a list of RETRIEVED CONTEXTS, identify which
facts from the ground truth are covered by the contexts.

Return JSON:
{
  "ground_truth_facts": ["fact 1", "fact 2", ...],
  "covered_facts": ["fact 1", ...],
  "coverage_ratio": <float 0.0-1.0>
}
"""


class RAGASEvaluator:
    """Evaluates RAG output quality on 3 RAGAS-inspired metrics.

    All scores are logged to MLflow for nightly reporting and trend tracking.
    Each evaluation also emits a Langfuse trace for per-request observability.

    Attributes:
        _http: Async HTTP client for LiteLLM + embedding service.
        _settings: Service configuration.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    @observe(name="ragas.evaluate")
    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
        tenant_id: str = "system",
        run_name: str | None = None,
    ) -> RAGASResult:
        """Run all 3 RAGAS metrics and log results to MLflow.

        Steps:
        1. faithfulness: LLM decomposes answer into claims → NLI check vs contexts
        2. answer_relevancy: cosine sim(embed(answer), embed(question))
        3. context_recall: if ground_truth provided → LLM coverage check

        Args:
            question: Original user question.
            answer: LLM-generated answer to evaluate.
            contexts: Retrieved context passages used to generate the answer.
            ground_truth: Optional reference answer for context_recall.
            tenant_id: Tenant identifier for MLflow experiment namespacing.
            run_name: Optional MLflow run name.

        Returns:
            RAGASResult with all scores and the MLflow run_id.
        """
        t0 = time.perf_counter()
        bound_log = log.bind(tenant_id=tenant_id)
        bound_log.info("ragas.evaluate.start", has_ground_truth=ground_truth is not None)

        # 1. Faithfulness
        faithfulness = await self._score_faithfulness(answer=answer, contexts=contexts)

        # 2. Answer relevancy (embedding cosine similarity)
        answer_relevancy = await self._score_answer_relevancy(
            question=question, answer=answer
        )

        # 3. Context recall (optional — requires ground truth)
        context_recall: float | None = None
        if ground_truth:
            context_recall = await self._score_context_recall(
                ground_truth=ground_truth, contexts=contexts
            )

        latency_ms = (time.perf_counter() - t0) * 1000

        # Log to MLflow
        run_id = await self._log_to_mlflow(
            tenant_id=tenant_id,
            question=question,
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_recall=context_recall,
            latency_ms=latency_ms,
            run_name=run_name,
        )

        result = RAGASResult(
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_recall=context_recall,
            run_id=run_id,
            tenant_id=tenant_id,
            latency_ms=round(latency_ms, 1),
        )

        bound_log.info(
            "ragas.evaluate.done",
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_recall=context_recall,
            latency_ms=round(latency_ms, 1),
        )
        return result

    # ── Metric Implementations ────────────────────────────────────────────────

    async def _score_faithfulness(
        self, answer: str, contexts: list[str]
    ) -> float:
        """NLI faithfulness: fraction of answer claims supported by contexts.

        Args:
            answer: LLM-generated answer.
            contexts: Retrieved context passages.

        Returns:
            Float score in [0.0, 1.0]. Returns 0.0 on error.
        """
        context_block = "\n\n".join(f"Context {i+1}: {c}" for i, c in enumerate(contexts))
        prompt = (
            f"ANSWER:\n{answer}\n\n"
            f"CONTEXTS:\n{context_block}\n\n"
            "Evaluate faithfulness as described."
        )
        try:
            raw = await self._llm_call(system=_FAITHFULNESS_SYSTEM, user=prompt)
            data = json.loads(raw)
            total = int(data.get("total_count", 0))
            supported = int(data.get("supported_count", 0))
            return min(1.0, supported / total) if total > 0 else 0.0
        except Exception as exc:
            log.warning("ragas.faithfulness.error", error=str(exc))
            return 0.0

    async def _score_answer_relevancy(
        self, question: str, answer: str
    ) -> float:
        """Cosine similarity between question and answer embeddings.

        Args:
            question: Original user question.
            answer: LLM-generated answer.

        Returns:
            Float score in [0.0, 1.0]. Returns 0.0 on error.
        """
        try:
            response = await self._http.post(
                f"{self._settings.embedding_service_url}/embed",
                json={"texts": [question, answer]},
                timeout=15.0,
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]
            q_vec = np.array(embeddings[0], dtype=np.float32)
            a_vec = np.array(embeddings[1], dtype=np.float32)

            # Cosine similarity
            similarity = float(
                np.dot(q_vec, a_vec)
                / (np.linalg.norm(q_vec) * np.linalg.norm(a_vec) + 1e-9)
            )
            return min(1.0, max(0.0, similarity))
        except Exception as exc:
            log.warning("ragas.answer_relevancy.error", error=str(exc))
            return 0.0

    async def _score_context_recall(
        self, ground_truth: str, contexts: list[str]
    ) -> float:
        """Coverage ratio: fraction of ground truth facts present in contexts.

        Args:
            ground_truth: Reference answer containing ground truth facts.
            contexts: Retrieved context passages.

        Returns:
            Float score in [0.0, 1.0]. Returns 0.0 on error.
        """
        context_block = "\n\n".join(f"Context {i+1}: {c}" for i, c in enumerate(contexts))
        prompt = (
            f"GROUND TRUTH:\n{ground_truth}\n\n"
            f"CONTEXTS:\n{context_block}\n\n"
            "Evaluate context recall as described."
        )
        try:
            raw = await self._llm_call(system=_CONTEXT_RECALL_SYSTEM, user=prompt)
            data = json.loads(raw)
            return min(1.0, max(0.0, float(data.get("coverage_ratio", 0.0))))
        except Exception as exc:
            log.warning("ragas.context_recall.error", error=str(exc))
            return 0.0

    # ── MLflow Logging ────────────────────────────────────────────────────────

    async def _log_to_mlflow(
        self,
        tenant_id: str,
        question: str,
        faithfulness: float,
        answer_relevancy: float,
        context_recall: float | None,
        latency_ms: float,
        run_name: str | None,
    ) -> str | None:
        """Log RAGAS metrics to MLflow experiment.

        Args:
            tenant_id: Used to namespace the MLflow experiment.
            question: Logged as a run tag.
            faithfulness: Metric value.
            answer_relevancy: Metric value.
            context_recall: Optional metric value.
            latency_ms: Total evaluation latency.
            run_name: Optional MLflow run name.

        Returns:
            MLflow run_id or None if logging fails.
        """
        try:
            mlflow.set_tracking_uri(self._settings.mlflow_tracking_uri)
            experiment_name = f"ragas_eval_{tenant_id}"

            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                mlflow.create_experiment(experiment_name)

            with mlflow.start_run(
                experiment_id=mlflow.get_experiment_by_name(experiment_name).experiment_id,
                run_name=run_name or f"ragas_{tenant_id}",
            ) as run:
                mlflow.log_metrics(
                    {
                        "faithfulness": faithfulness,
                        "answer_relevancy": answer_relevancy,
                        "eval_latency_ms": latency_ms,
                        **({"context_recall": context_recall} if context_recall is not None else {}),
                    }
                )
                mlflow.set_tags(
                    {
                        "tenant_id": tenant_id,
                        "question_preview": question[:100],
                    }
                )
                return run.info.run_id

        except Exception as exc:
            log.warning("ragas.mlflow_log.failed", error=str(exc))
            return None

    # ── LLM Call ─────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _llm_call(self, system: str, user: str) -> str:
        """Call LiteLLM proxy with JSON output enforced.

        Args:
            system: System prompt.
            user: User message.

        Returns:
            Raw content string from LLM.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
        """
        payload: dict[str, Any] = {
            "model": self._settings.ragas_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }
        response = await self._http.post(
            f"{self._settings.litellm_url}/chat/completions",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
