"""
RAG API — GraphRAG Entity & Relationship Extractor.
Day 22: Phase 5 — LLM-powered entity/relationship extraction for knowledge graph construction.

Calls LiteLLM proxy with structured JSON output to extract entities and
relationships from arbitrary text, then feeds the result to Neo4j.

Protocols: None
SOLID: SRP (extraction only), OCP (swap model via config), DIP (http client injected)
"""

from __future__ import annotations

import json
import uuid

import httpx
import structlog
from langfuse.decorators import observe
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_api.config import Settings
from rag_api.models import Entity, ExtractedGraph, Relationship

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a knowledge graph extraction expert. Given a text passage, extract:
1. ENTITIES: people, organizations, concepts, metrics, locations, events.
2. RELATIONSHIPS: directed relations between entities.

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {"id": "e1", "name": "Entity Name", "type": "person|org|concept|metric|location|event", "description": "brief description"}
  ],
  "relationships": [
    {"source_id": "e1", "target_id": "e2", "relation": "relationship_label", "weight": 1.0}
  ]
}

Rules:
- Entity IDs must be stable short strings (e.g. "e1", "entity_openai")
- Relation labels should be concise (e.g. "founded", "acquired", "reports_to", "depends_on")
- Weight 1.0 = strongly asserted, 0.5 = implied
- Return empty arrays if nothing found, never null
"""


class EntityExtractor:
    """Extracts entities and relationships from text via LLM structured output.

    Uses LiteLLM proxy to call the configured graphrag_model. The system
    prompt enforces strict JSON output. Falls back to an empty graph on
    parsing failure so the pipeline never hard-fails.

    Attributes:
        _http: Async HTTP client.
        _settings: Service configuration.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    @observe(name="graphrag.extract_entities")
    async def extract(self, text: str, tenant_id: str) -> ExtractedGraph:
        """Extract entities and relationships from a text passage.

        Args:
            text: Source text to analyse (max ~4000 tokens).
            tenant_id: Tenant identifier for Langfuse trace tagging.

        Returns:
            ExtractedGraph with entities and relationships. Returns an empty
            graph (not an exception) if extraction fails.
        """
        truncated = text[:8000]  # Avoid token overflow

        bound_log = log.bind(tenant_id=tenant_id, text_length=len(text))
        bound_log.info("graphrag.extract.start")

        try:
            raw_json = await self._call_llm(truncated)
            graph = _parse_graph(raw_json, source_text=truncated)
            bound_log.info(
                "graphrag.extract.done",
                entities=len(graph.entities),
                relationships=len(graph.relationships),
            )
            return graph

        except Exception as exc:
            bound_log.error("graphrag.extract.failed", error=str(exc))
            return ExtractedGraph(entities=[], relationships=[], source_text=truncated)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def _call_llm(self, text: str) -> str:
        """Call LiteLLM proxy for entity extraction.

        Args:
            text: Text to analyse.

        Returns:
            Raw JSON string from the LLM.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            ValueError: If LLM response cannot be parsed as JSON.
        """
        payload = {
            "model": self._settings.graphrag_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract entities and relationships from this text:\n\n{text}",
                },
            ],
            "temperature": 0.1,  # Low temperature for deterministic structured output
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }

        response = await self._http.post(
            f"{self._settings.litellm_url}/chat/completions",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_graph(raw_json: str, source_text: str) -> ExtractedGraph:
    """Parse raw LLM JSON output into an ExtractedGraph.

    Args:
        raw_json: JSON string from LLM.
        source_text: Original text (stored for reference).

    Returns:
        ExtractedGraph with typed Entity and Relationship objects.

    Raises:
        ValueError: If JSON is malformed or missing required fields.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    entities: list[Entity] = []
    for item in data.get("entities", []):
        entities.append(
            Entity(
                id=str(item.get("id", str(uuid.uuid4())[:8])),
                name=str(item.get("name", "")),
                entity_type=str(item.get("type", "concept")),
                description=str(item.get("description", "")),
            )
        )

    relationships: list[Relationship] = []
    for item in data.get("relationships", []):
        relationships.append(
            Relationship(
                source_id=str(item.get("source_id", "")),
                target_id=str(item.get("target_id", "")),
                relation=str(item.get("relation", "related_to")),
                weight=float(item.get("weight", 1.0)),
            )
        )

    return ExtractedGraph(
        entities=entities,
        relationships=relationships,
        source_text=source_text,
    )
