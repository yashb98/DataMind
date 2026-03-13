"""
dbt Lineage Tracker — extracts model DAG from dbt manifest.json + optional Neo4j persistence.
Day 11: Phase 2 — OpenLineage-compatible lineage from dbt manifest.

Protocols: None
SOLID: SRP (lineage only), OCP (ILineageProvider ABC), DIP (injected via lifespan)
Benchmark: tests/benchmarks/bench_dbt.py
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import structlog

from mcp_dbt_runner.config import settings
from mcp_dbt_runner.models import GetLineageResponse

log = structlog.get_logger(__name__)


class ILineageProvider(ABC):
    """Abstract interface for dbt lineage retrieval.

    SOLID OCP: alternative providers (e.g., OpenLineage HTTP, Marquez) add
    new files implementing this interface — zero modification to callers.
    """

    @abstractmethod
    async def get_lineage(
        self,
        model_name: str,
        tenant_id: str,
        direction: str,
        depth: int,
    ) -> GetLineageResponse:
        """Retrieve upstream/downstream lineage for a dbt model.

        Args:
            model_name: dbt model name to query.
            tenant_id: Tenant identifier (used for Neo4j filtering).
            direction: One of 'upstream', 'downstream', or 'both'.
            depth: Maximum hops to traverse in each direction.

        Returns:
            GetLineageResponse with upstream, downstream, sources, exposures.
        """
        ...


class ManifestLineageProvider(ILineageProvider):
    """Reads model DAG lineage from dbt manifest.json (fast, offline).

    The manifest is lazy-loaded on first call and then cached in memory.
    If the manifest file does not exist (e.g., dbt compile has not been run)
    the provider returns an empty response rather than raising an exception,
    allowing the service to start and accept health checks regardless.

    Thread-safety: The manifest cache is set once and never mutated, so
    concurrent async reads are safe.
    """

    def __init__(self) -> None:
        self._manifest: dict[str, Any] | None = None

    def _load_manifest(self) -> dict[str, Any]:
        """Load (and cache) the dbt manifest.json from disk.

        Returns:
            Parsed manifest dict, or a minimal empty structure if the file
            does not exist or cannot be parsed.
        """
        if self._manifest is not None:
            return self._manifest

        manifest_path = os.path.join(settings.dbt_project_dir, "target", "manifest.json")
        try:
            with open(manifest_path) as fh:
                self._manifest = json.load(fh)
            log.info("dbt.manifest.loaded", path=manifest_path)
        except FileNotFoundError:
            log.warning("dbt.manifest.missing", path=manifest_path)
            self._manifest = {"nodes": {}, "sources": {}, "exposures": {}}
        except json.JSONDecodeError as exc:
            log.error("dbt.manifest.parse_error", path=manifest_path, error=str(exc))
            self._manifest = {"nodes": {}, "sources": {}, "exposures": {}}

        return self._manifest

    async def get_lineage(
        self,
        model_name: str,
        tenant_id: str,
        direction: str,
        depth: int,
    ) -> GetLineageResponse:
        """Resolve upstream and downstream lineage from manifest.json.

        Args:
            model_name: Target model name (e.g., ``stg_orders``).
            tenant_id: Tenant identifier (informational; manifest is shared).
            direction: ``'upstream'``, ``'downstream'``, or ``'both'``.
            depth: Caps the number of dependency hops returned (multiplied by
                3 to account for wide graphs; actual graph traversal is
                single-hop from the target node).

        Returns:
            GetLineageResponse with populated upstream, downstream, sources,
            exposures, and a plain-English dag_summary.
        """
        manifest = self._load_manifest()
        nodes: dict[str, Any] = manifest.get("nodes", {})
        exposures_map: dict[str, Any] = manifest.get("exposures", {})

        # Locate the node key matching model_name (e.g., "model.project.stg_orders")
        node_key: str | None = next(
            (
                k
                for k in nodes
                if k.endswith(f".{model_name}") or model_name in k
            ),
            None,
        )

        upstream: list[str] = []
        downstream: list[str] = []
        sources: list[str] = []
        exposures: list[str] = []

        if node_key:
            node = nodes[node_key]
            depends_on_nodes: list[str] = node.get("depends_on", {}).get("nodes", [])

            for dep in depends_on_nodes:
                parts = dep.split(".")
                dep_name = parts[-1] if parts else dep
                if dep.startswith("source."):
                    sources.append(dep_name)
                elif direction in ("upstream", "both"):
                    upstream.append(dep_name)

            # Downstream: scan all nodes for references to this node
            if direction in ("downstream", "both"):
                for nk, nv in nodes.items():
                    if nk == node_key:
                        continue
                    nv_deps: list[str] = nv.get("depends_on", {}).get("nodes", [])
                    if node_key in nv_deps:
                        downstream.append(nk.split(".")[-1])

            # Exposures referencing this node
            for exp_key, exp_val in exposures_map.items():
                exp_deps: list[str] = exp_val.get("depends_on", {}).get("nodes", [])
                if node_key in exp_deps:
                    exposures.append(exp_key.split(".")[-1])

        max_results = depth * 3
        dag_summary = (
            f"Model '{model_name}': "
            f"{len(upstream)} upstream, {len(downstream)} downstream, "
            f"{len(sources)} sources, {len(exposures)} exposures"
        )

        log.info(
            "dbt.lineage.resolved",
            model=model_name,
            upstream=len(upstream),
            downstream=len(downstream),
            sources=len(sources),
        )

        return GetLineageResponse(
            model_name=model_name,
            upstream=upstream[:max_results],
            downstream=downstream[:max_results],
            sources=sources,
            exposures=exposures,
            dag_summary=dag_summary,
        )


class Neo4jLineagePersister:
    """Persists dbt lineage edges to Neo4j for GraphRAG / audit queries.

    This is a write-side component used alongside ManifestLineageProvider.
    It is separate (SRP) so the read path never depends on Neo4j availability.
    """

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    async def persist(
        self,
        model_name: str,
        tenant_id: str,
        response: GetLineageResponse,
    ) -> None:
        """Write lineage edges to Neo4j.

        Creates ``(:DbtModel)`` nodes and ``[:DEPENDS_ON]`` / ``[:HAS_SOURCE]``
        relationships. Uses MERGE to avoid duplicates on repeated runs.

        Args:
            model_name: Central model node name.
            tenant_id: Tenant identifier stored on each node.
            response: Lineage response containing upstream/downstream/sources.
        """
        try:
            async with self._driver.session() as session:
                # Upsert the central model node
                await session.run(
                    "MERGE (m:DbtModel {name: $name, tenant_id: $tenant_id})",
                    name=model_name,
                    tenant_id=tenant_id,
                )
                # Upstream edges
                for dep in response.upstream:
                    await session.run(
                        """
                        MERGE (d:DbtModel {name: $dep, tenant_id: $tid})
                        MERGE (m:DbtModel {name: $model, tenant_id: $tid})
                        MERGE (m)-[:DEPENDS_ON]->(d)
                        """,
                        dep=dep,
                        model=model_name,
                        tid=tenant_id,
                    )
                # Source edges
                for src in response.sources:
                    await session.run(
                        """
                        MERGE (s:DbtSource {name: $src, tenant_id: $tid})
                        MERGE (m:DbtModel {name: $model, tenant_id: $tid})
                        MERGE (m)-[:HAS_SOURCE]->(s)
                        """,
                        src=src,
                        model=model_name,
                        tid=tenant_id,
                    )
            log.info("dbt.lineage.persisted", model=model_name, tenant_id=tenant_id)
        except Exception as exc:
            # Non-fatal: lineage persistence is best-effort
            log.warning("dbt.lineage.persist_failed", model=model_name, error=str(exc))
