"""
RAG API — Neo4j GraphRAG Store.
Day 22: Phase 5 — Tenant-isolated entity/relationship graph with community summary queries.

Node label: Entity | Relationship type: RELATED_TO
All nodes carry a tenant_id property for isolation.

Protocols: None
SOLID: SRP (Neo4j persistence only), OCP (new query types = new method), DIP (driver injected)
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncDriver

from rag_api.config import Settings
from rag_api.models import Entity, Relationship

log = structlog.get_logger(__name__)


class GraphRAGStore:
    """Neo4j-backed storage for knowledge graph entities and relationships.

    All write operations use MERGE to be idempotent. All queries carry
    a ``tenant_id`` filter to enforce multi-tenant isolation.

    Attributes:
        _driver: Async Neo4j driver.
        _settings: Service configuration.
    """

    def __init__(self, driver: AsyncDriver, settings: Settings) -> None:
        self._driver = driver
        self._settings = settings

    async def ensure_constraints(self) -> None:
        """Create uniqueness constraints for Entity nodes on first startup."""
        async with self._driver.session() as session:
            try:
                await session.run(
                    "CREATE CONSTRAINT entity_unique IF NOT EXISTS "
                    "FOR (e:Entity) REQUIRE (e.entity_id, e.tenant_id) IS UNIQUE"
                )
            except Exception as exc:
                log.warning("graphrag.constraint_skip", reason=str(exc))

    # ── Write Operations ──────────────────────────────────────────────────────

    async def upsert_entities(
        self, tenant_id: str, entities: list[Entity]
    ) -> None:
        """Upsert Entity nodes into Neo4j (idempotent MERGE).

        Args:
            tenant_id: Tenant isolation key added to every node.
            entities: Entities extracted from a text passage.
        """
        if not entities:
            return

        async with self._driver.session() as session:
            for entity in entities:
                await session.run(
                    """
                    MERGE (e:Entity {entity_id: $entity_id, tenant_id: $tenant_id})
                    SET e.name = $name,
                        e.type = $type,
                        e.description = $description,
                        e.updated_at = datetime()
                    """,
                    entity_id=entity.id,
                    tenant_id=tenant_id,
                    name=entity.name,
                    type=entity.entity_type,
                    description=entity.description,
                )

        log.debug(
            "graphrag.entities_upserted",
            count=len(entities),
            tenant_id=tenant_id,
        )

    async def upsert_relationships(
        self, tenant_id: str, relationships: list[Relationship]
    ) -> None:
        """Upsert RELATED_TO edges between Entity nodes.

        Skips any relationship whose source_id or target_id does not match
        an existing node (referential integrity). Logs a warning instead of
        raising so the pipeline continues.

        Args:
            tenant_id: Tenant isolation key.
            relationships: Relationships extracted from a text passage.
        """
        if not relationships:
            return

        async with self._driver.session() as session:
            for rel in relationships:
                try:
                    await session.run(
                        """
                        MATCH (src:Entity {entity_id: $source_id, tenant_id: $tenant_id})
                        MATCH (tgt:Entity {entity_id: $target_id, tenant_id: $tenant_id})
                        MERGE (src)-[r:RELATED_TO {relation: $relation}]->(tgt)
                        SET r.weight = $weight,
                            r.updated_at = datetime()
                        """,
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        tenant_id=tenant_id,
                        relation=rel.relation,
                        weight=rel.weight,
                    )
                except Exception as exc:
                    log.warning(
                        "graphrag.relationship_skip",
                        source=rel.source_id,
                        target=rel.target_id,
                        error=str(exc),
                    )

        log.debug(
            "graphrag.relationships_upserted",
            count=len(relationships),
            tenant_id=tenant_id,
        )

    # ── Read Operations ───────────────────────────────────────────────────────

    async def get_community_summaries(
        self,
        tenant_id: str,
        query_entities: list[str],
        max_hops: int = 2,
        limit: int = 10,
    ) -> list[str]:
        """Traverse the knowledge graph and return community context strings.

        Performs a 1..max_hops neighbourhood traversal from all entities
        whose name matches ``query_entities``. Returns entity descriptions
        as community context for use in RAG prompts.

        Args:
            tenant_id: Tenant isolation key.
            query_entities: Entity names to start traversal from.
            max_hops: Maximum graph hops (default 2).
            limit: Maximum related entities to return.

        Returns:
            List of description strings from neighbourhood nodes.
        """
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH (e:Entity {{tenant_id: $tenant_id}})
                WHERE e.name IN $entity_names
                MATCH (e)-[:RELATED_TO*1..{max_hops}]-(n:Entity {{tenant_id: $tenant_id}})
                WHERE n.name NOT IN $entity_names
                WITH DISTINCT n
                WHERE n.description IS NOT NULL AND n.description <> ''
                RETURN n.name AS name, n.type AS type, n.description AS description
                ORDER BY n.name
                LIMIT $limit
                """,
                tenant_id=tenant_id,
                entity_names=query_entities,
                limit=limit,
            )
            records = await result.data()

        summaries: list[str] = []
        for record in records:
            name = record.get("name", "")
            entity_type = record.get("type", "")
            description = record.get("description", "")
            if description:
                summaries.append(f"[{entity_type}] {name}: {description}")

        return summaries

    async def get_neighbours(
        self,
        tenant_id: str,
        entity_name: str,
        max_hops: int = 2,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get neighbourhood entities for a named entity.

        Args:
            tenant_id: Tenant isolation key.
            entity_name: Entity to start from.
            max_hops: Maximum graph hops.
            limit: Max neighbours to return.

        Returns:
            List of {name, type, description, min_hops} dicts.
        """
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH path = (e:Entity {{name: $entity_name, tenant_id: $tenant_id}})
                    -[:RELATED_TO*1..{max_hops}]-(related:Entity {{tenant_id: $tenant_id}})
                WITH related, min(length(path)) AS min_hops
                WHERE related.name <> $entity_name
                RETURN DISTINCT
                    related.name AS name,
                    related.type AS type,
                    related.description AS description,
                    min_hops
                ORDER BY min_hops ASC, related.name
                LIMIT $limit
                """,
                entity_name=entity_name,
                tenant_id=tenant_id,
                limit=limit,
            )
            return await result.data()

    # ── DSR Erasure ───────────────────────────────────────────────────────────

    async def delete_tenant(self, tenant_id: str) -> int:
        """Delete ALL nodes and relationships for a tenant (GDPR Art.17).

        Uses DETACH DELETE to remove all edges before deleting nodes.
        Counts deleted nodes for DSR audit trail.

        Args:
            tenant_id: Tenant whose graph data to erase.

        Returns:
            Count of deleted nodes.
        """
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (n {tenant_id: $tenant_id})
                WITH n, count(n) AS cnt
                DETACH DELETE n
                RETURN sum(cnt) AS deleted
                """,
                tenant_id=tenant_id,
            )
            record = await result.single()
            deleted = int(record["deleted"]) if record and record["deleted"] else 0

        log.info("graphrag.tenant_erased", tenant_id=tenant_id, nodes_deleted=deleted)
        return deleted
