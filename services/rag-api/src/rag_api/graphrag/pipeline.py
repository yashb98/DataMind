"""
RAG API — GraphRAG Pipeline Orchestrator.
Day 22: Phase 5 — End-to-end orchestration of entity extraction → Neo4j storage → community retrieval.

Protocols: None
SOLID: SRP (pipeline coordination only), DIP (extractor + store injected)
"""

from __future__ import annotations

import structlog

from rag_api.graphrag.extractor import EntityExtractor
from rag_api.graphrag.neo4j_store import GraphRAGStore
from rag_api.models import ExtractedGraph, GraphIngestResponse, GraphSearchResponse

log = structlog.get_logger(__name__)


class GraphRAGPipeline:
    """Orchestrates the full GraphRAG ingestion and retrieval pipeline.

    Ingestion: text → EntityExtractor → Neo4j (entities + relationships)
    Retrieval: query entities → Neo4j community traversal → context strings

    Attributes:
        _extractor: Entity + relationship extractor.
        _store: Neo4j graph store.
    """

    def __init__(self, extractor: EntityExtractor, store: GraphRAGStore) -> None:
        self._extractor = extractor
        self._store = store

    async def ingest(
        self,
        text: str,
        tenant_id: str,
        source_id: str = "",
    ) -> GraphIngestResponse:
        """Extract entities and relationships from text, persist to Neo4j.

        Args:
            text: Source text to analyse.
            tenant_id: Tenant isolation key.
            source_id: Optional source document identifier.

        Returns:
            GraphIngestResponse with counts of upserted nodes and edges.
        """
        bound_log = log.bind(tenant_id=tenant_id, source_id=source_id)
        bound_log.info("graphrag.ingest.start", text_length=len(text))

        graph: ExtractedGraph = await self._extractor.extract(text=text, tenant_id=tenant_id)

        if graph.entities:
            await self._store.upsert_entities(tenant_id=tenant_id, entities=graph.entities)

        if graph.relationships:
            await self._store.upsert_relationships(
                tenant_id=tenant_id, relationships=graph.relationships
            )

        bound_log.info(
            "graphrag.ingest.done",
            entities=len(graph.entities),
            relationships=len(graph.relationships),
        )

        return GraphIngestResponse(
            tenant_id=tenant_id,
            entities_upserted=len(graph.entities),
            relationships_upserted=len(graph.relationships),
            source_id=source_id,
        )

    async def search(
        self,
        query: str,
        tenant_id: str,
        max_hops: int = 2,
        limit: int = 10,
    ) -> GraphSearchResponse:
        """Retrieve community context for a natural language query.

        Extracts query entities inline (lightweight extraction), then traverses
        the Neo4j graph to surface related community descriptions.

        Args:
            query: Natural language query.
            tenant_id: Tenant isolation key.
            max_hops: Maximum graph traversal depth.
            limit: Max entities to return.

        Returns:
            GraphSearchResponse with community summaries and related entities.
        """
        bound_log = log.bind(tenant_id=tenant_id)

        # Extract entities from the query itself
        query_graph: ExtractedGraph = await self._extractor.extract(
            text=query, tenant_id=tenant_id
        )
        query_entity_names = [e.name for e in query_graph.entities] if query_graph.entities else []

        if not query_entity_names:
            # Fallback: use the raw query as a single entity name
            query_entity_names = [query.strip()[:50]]

        # Community traversal
        summaries = await self._store.get_community_summaries(
            tenant_id=tenant_id,
            query_entities=query_entity_names,
            max_hops=max_hops,
            limit=limit,
        )

        # Direct neighbour details
        neighbours: list[dict] = []  # type: ignore[type-arg]
        for entity_name in query_entity_names[:3]:  # Limit to avoid over-querying
            nbrs = await self._store.get_neighbours(
                tenant_id=tenant_id,
                entity_name=entity_name,
                max_hops=max_hops,
                limit=limit // max(len(query_entity_names), 1),
            )
            neighbours.extend(nbrs)

        # Deduplicate neighbours by name
        seen_names: set[str] = set()
        unique_neighbours: list[dict] = []  # type: ignore[type-arg]
        for n in neighbours:
            name = str(n.get("name", ""))
            if name not in seen_names:
                seen_names.add(name)
                unique_neighbours.append(n)

        bound_log.info(
            "graphrag.search.done",
            query_entities=query_entity_names,
            summaries=len(summaries),
            neighbours=len(unique_neighbours),
        )

        return GraphSearchResponse(
            query=query,
            tenant_id=tenant_id,
            community_summaries=summaries,
            entities_found=unique_neighbours,
            total=len(unique_neighbours),
        )
