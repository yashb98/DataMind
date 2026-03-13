"""
NarrativeAgent — generates structured narrative sections from data + retrieved context.
Day 22: Phase 5 RAG & Reporting.

Protocols: None
SOLID: SRP (generates narrative only), OCP (ISection implementations), DIP (litellm_url injected)
Benchmark: tests/benchmarks/bench_narrative.py — target < 15s per section
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

import httpx
import structlog
from langfuse.decorators import observe
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

# System prompt enforcing citations for every factual claim
_SYSTEM_PROMPT = (
    "You are a senior data analyst generating professional narrative reports. "
    "You MUST cite every factual claim using [SOURCE chunk_id] notation where chunk_id "
    "is one of the provided context chunk IDs. "
    "Rules:\n"
    "1. Every numerical figure must be followed by a [SOURCE ...] citation.\n"
    "2. Every trend or insight claim must be followed by a [SOURCE ...] citation.\n"
    "3. Uncited claims will be flagged as hallucinations and rejected.\n"
    "4. Write in professional, concise business prose.\n"
    "5. Structure your response in paragraphs, not bullet points.\n"
    "6. If the provided context does not support a claim, write "
    "'Insufficient data to support this analysis.'"
)

_SECTION_TYPE_GUIDANCE: dict[str, str] = {
    "summary": (
        "Write a 2-3 paragraph executive summary. Lead with the most important finding. "
        "Keep total length under 300 words."
    ),
    "analysis": (
        "Write a detailed analytical section of 3-5 paragraphs. "
        "Explain patterns, correlations, and drivers observed in the data."
    ),
    "recommendation": (
        "Write 3-5 concrete, actionable recommendations. "
        "Each recommendation must be directly supported by the data context provided."
    ),
    "methodology": (
        "Describe the analytical approach, data sources used, and any limitations. "
        "Be precise about statistical methods and assumptions."
    ),
}

_CITATION_RE = re.compile(r"\[SOURCE\s+([^\]]+)\]")


@dataclass
class NarrativeSection:
    """A generated narrative section with citations and confidence score."""

    section_id: str
    title: str
    body: str
    citations: list[str]
    confidence: float
    generation_ms: float = 0.0
    section_type: str = "analysis"


class NarrativeAgent:
    """Generates narrative sections from data insights + RAG context.

    Uses Claude Sonnet 4 via LiteLLM with Langfuse tracing.
    Enforces citation of retrieved chunks via [SOURCE chunk_id] notation.
    Confidence is computed as the fraction of sentences containing at least
    one citation.

    Args:
        litellm_url: Base URL of the LiteLLM proxy, e.g. ``http://litellm:4000``.
        langfuse_settings: Reserved for future Langfuse SDK configuration.
    """

    def __init__(self, litellm_url: str, langfuse_settings: dict | None = None) -> None:
        self._litellm_url = litellm_url.rstrip("/")
        self._langfuse_settings = langfuse_settings or {}
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Initialise the shared HTTP client."""
        self._client = httpx.AsyncClient(timeout=60.0)
        log.info("narrative_agent.started", litellm_url=self._litellm_url)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
        log.info("narrative_agent.stopped")

    @observe(name="narrative.generate_section")
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def generate_section(
        self,
        title: str,
        data_context: dict,
        retrieved_chunks: list[dict],
        tenant_id: str,
        section_type: str = "analysis",
    ) -> NarrativeSection:
        """Generate a single narrative section with citation-grounded content.

        Args:
            title: Section heading shown in the compiled report.
            data_context: Dict of key metrics, aggregates, or table previews.
            retrieved_chunks: List of RAG chunks; each dict must contain
                ``chunk_id``, ``source_id``, and ``content`` keys.
            tenant_id: Owning tenant for logging / isolation.
            section_type: One of ``summary``, ``analysis``, ``recommendation``,
                ``methodology``. Governs the system-prompt guidance appended.

        Returns:
            NarrativeSection with ``body``, ``citations`` extracted from
            ``[SOURCE ...]`` tags, and ``confidence`` in [0, 1].

        Raises:
            RuntimeError: If the LiteLLM call fails after retries.
        """
        start = time.perf_counter()

        if self._client is None:
            raise RuntimeError("NarrativeAgent not started — call startup() first")

        section_id = str(uuid.uuid4())
        guidance = _SECTION_TYPE_GUIDANCE.get(section_type, _SECTION_TYPE_GUIDANCE["analysis"])

        # Build context block from retrieved chunks
        context_lines: list[str] = []
        for chunk in retrieved_chunks:
            cid = chunk.get("chunk_id", "unknown")
            content = chunk.get("content", "")
            context_lines.append(f"[CHUNK {cid}]\n{content}")
        context_block = "\n\n".join(context_lines) if context_lines else "No context provided."

        # Build data summary
        data_lines: list[str] = []
        for k, v in data_context.items():
            data_lines.append(f"  {k}: {v}")
        data_summary = "\n".join(data_lines) if data_lines else "  No structured data provided."

        user_message = (
            f"Section Title: {title}\n"
            f"Section Type: {section_type}\n"
            f"Guidance: {guidance}\n\n"
            f"--- DATA CONTEXT ---\n{data_summary}\n\n"
            f"--- RETRIEVED CONTEXT CHUNKS ---\n{context_block}\n\n"
            "Write the narrative section now. Remember to cite every factual claim "
            "using [SOURCE chunk_id] notation from the chunks above."
        )

        payload = {
            "model": "claude-sonnet-4-5",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 2000,
            "temperature": 0.3,
            "metadata": {
                "tenant_id": tenant_id,
                "section_id": section_id,
                "section_type": section_type,
            },
        }

        try:
            response = await self._client.post(
                f"{self._litellm_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "narrative.llm.http_error",
                status=exc.response.status_code,
                section_id=section_id,
                tenant_id=tenant_id,
            )
            raise RuntimeError(f"LiteLLM HTTP error {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            log.error("narrative.llm.request_error", error=str(exc), section_id=section_id)
            raise RuntimeError(f"LiteLLM request failed: {exc}") from exc

        body = response.json()["choices"][0]["message"]["content"].strip()
        citations = _extract_citations(body)
        confidence = _compute_confidence(body)

        elapsed_ms = (time.perf_counter() - start) * 1000

        log.info(
            "narrative.section.generated",
            section_id=section_id,
            title=title,
            section_type=section_type,
            citations=len(citations),
            confidence=round(confidence, 3),
            elapsed_ms=round(elapsed_ms, 2),
            tenant_id=tenant_id,
        )

        return NarrativeSection(
            section_id=section_id,
            title=title,
            body=body,
            citations=list(set(citations)),
            confidence=confidence,
            generation_ms=elapsed_ms,
            section_type=section_type,
        )

    @observe(name="narrative.generate_report")
    async def generate_report(
        self,
        sections_spec: list[dict],
        retrieved_chunks: list[dict],
        tenant_id: str,
    ) -> list[NarrativeSection]:
        """Generate all sections for a report concurrently.

        Args:
            sections_spec: List of dicts with keys ``title``, ``type``,
                ``data_context``.
            retrieved_chunks: Shared RAG context available to all sections.
            tenant_id: Owning tenant.

        Returns:
            Ordered list of NarrativeSection objects.
        """
        import asyncio

        tasks = [
            self.generate_section(
                title=spec["title"],
                data_context=spec.get("data_context", {}),
                retrieved_chunks=retrieved_chunks,
                tenant_id=tenant_id,
                section_type=spec.get("type", "analysis"),
            )
            for spec in sections_spec
        ]
        return list(await asyncio.gather(*tasks))


# ── Private helpers ────────────────────────────────────────────────────────────


def _extract_citations(body: str) -> list[str]:
    """Extract all [SOURCE chunk_id] values from the narrative body.

    Args:
        body: Raw LLM response text.

    Returns:
        List of chunk_id strings found in citation tags.
    """
    return _CITATION_RE.findall(body)


def _compute_confidence(body: str) -> float:
    """Compute confidence as fraction of sentences containing at least one citation.

    A sentence ending with [SOURCE ...] is considered grounded. Sentences with
    no citation are penalised proportionally.

    Args:
        body: Raw LLM response text.

    Returns:
        Float in [0, 1]. Returns 0.5 for empty body (neutral default).
    """
    # Split on sentence-ending punctuation followed by whitespace or end
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    if not sentences:
        return 0.5
    cited = sum(1 for s in sentences if _CITATION_RE.search(s))
    return round(cited / len(sentences), 3)
