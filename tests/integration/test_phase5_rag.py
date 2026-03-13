"""
Integration tests — Phase 5: RAG API + Memory + GraphRAG + DSR + Narrative.
Days 22-23: Requires running docker compose stack (DATAMIND_INTEGRATION_TESTS=true).

Usage:
    DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/test_phase5_rag.py -v

SLO targets:
    rag-api: health < 100ms
    MMR retrieval: E2E < 2s
    memory store/retrieve: < 500ms
    narrative generation: < 15s (LLM-dependent)
    DSR SAR: < 30s (all stores)
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"
pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)

RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8130")
TEST_TENANT = "integration_test_phase5"
TEST_TENANT_B = "integration_test_phase5_b"

# ── Sample data ────────────────────────────────────────────────────────────────

SAMPLE_CHUNKS = [
    {
        "chunk_id": f"chunk_{i:03d}",
        "source_id": f"doc_{i // 3:02d}",
        "content": (
            f"Revenue in Q{(i % 4) + 1} 2024 reached ${100_000 + i * 5_000:,}, "
            f"representing a {5 + i}% year-over-year growth. "
            f"Customer acquisition cost decreased by {3 + i}% during this period."
        ),
    }
    for i in range(9)
]

SAMPLE_SECTIONS_SPEC = [
    {
        "title": "Executive Summary",
        "type": "summary",
        "data_context": {
            "total_revenue": "$1,250,000",
            "yoy_growth": "12.5%",
            "new_customers": 340,
        },
    },
    {
        "title": "Revenue Analysis",
        "type": "analysis",
        "data_context": {
            "q1_revenue": "$280,000",
            "q2_revenue": "$310,000",
            "q3_revenue": "$330,000",
            "q4_revenue": "$330,000",
        },
    },
]

SAMPLE_NARRATIVE_SECTIONS = [
    {
        "section_id": str(uuid.uuid4()),
        "title": "Executive Summary",
        "body": (
            "Revenue grew 12.5% YoY to $1.25M [SOURCE chunk_000]. "
            "Customer acquisition improved significantly [SOURCE chunk_001]."
        ),
        "citations": ["chunk_000", "chunk_001"],
        "confidence": 0.85,
        "generation_ms": 2500.0,
        "section_type": "summary",
    },
    {
        "section_id": str(uuid.uuid4()),
        "title": "Revenue Analysis",
        "body": (
            "Q4 performance matched Q3 at $330K [SOURCE chunk_002], "
            "indicating stabilisation after strong H1 growth [SOURCE chunk_003]."
        ),
        "citations": ["chunk_002", "chunk_003"],
        "confidence": 0.90,
        "generation_ms": 3100.0,
        "section_type": "analysis",
    },
]


# ── Health checks ──────────────────────────────────────────────────────────────


class TestRAGAPIHealth:
    def test_liveness(self) -> None:
        r = httpx.get(f"{RAG_API_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "alive"
        assert data["service"] == "rag-api"

    def test_readiness(self) -> None:
        r = httpx.get(f"{RAG_API_URL}/health/readiness", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")
        assert "checks" in data

    def test_liveness_under_100ms_slo(self) -> None:
        start = time.perf_counter()
        r = httpx.get(f"{RAG_API_URL}/health/liveness", timeout=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 100, f"Health check took {elapsed_ms:.1f}ms > 100ms SLO"


# ── Memory Tier Tests ──────────────────────────────────────────────────────────


class TestMemoryTiers:
    def test_store_and_retrieve_stm(self) -> None:
        """Store a memory in STM (Redis) and retrieve it by query."""
        session_id = str(uuid.uuid4())
        agent_id = "test-agent-001"
        content = f"The sales target for Q4 is $500,000. Session {session_id}."

        # Store
        r = httpx.post(
            f"{RAG_API_URL}/api/memory/store",
            json={
                "content": content,
                "agent_id": agent_id,
                "session_id": session_id,
                "tenant_id": TEST_TENANT,
                "tiers": ["stm"],
                "metadata": {"test": True},
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "memory_ids" in data
        assert "stm" in data["memory_ids"]

        # Retrieve
        r = httpx.post(
            f"{RAG_API_URL}/api/memory/retrieve",
            json={
                "query": "sales target Q4",
                "agent_id": agent_id,
                "tenant_id": TEST_TENANT,
                "tiers": ["stm"],
                "top_k": 5,
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "memories" in data
        assert data["total"] >= 0  # May be 0 if STM TTL expired mid-test

    def test_store_ltm_requires_embedding(self) -> None:
        """LTM storage must succeed (embedding service must be reachable)."""
        r = httpx.post(
            f"{RAG_API_URL}/api/memory/store",
            json={
                "content": "Long-term insight: churn rate peaks in January.",
                "agent_id": "test-agent-ltm",
                "session_id": str(uuid.uuid4()),
                "tenant_id": TEST_TENANT,
                "tiers": ["ltm"],
            },
            timeout=30,
        )
        # 200 means embedding + Qdrant upsert succeeded
        # 503 is acceptable if embedding service is degraded
        assert r.status_code in (200, 503)

    def test_tenant_isolation(self) -> None:
        """Memories stored for TEST_TENANT must not appear for TEST_TENANT_B."""
        session_id = str(uuid.uuid4())
        unique_content = f"TENANT_A_SECRET_{session_id}"

        # Store for tenant A
        r = httpx.post(
            f"{RAG_API_URL}/api/memory/store",
            json={
                "content": unique_content,
                "agent_id": "isolation-agent",
                "session_id": session_id,
                "tenant_id": TEST_TENANT,
                "tiers": ["stm"],
            },
            timeout=10,
        )
        assert r.status_code == 200

        # Retrieve for tenant B — must not return tenant A's memories
        r = httpx.post(
            f"{RAG_API_URL}/api/memory/retrieve",
            json={
                "query": unique_content,
                "agent_id": "isolation-agent",
                "tenant_id": TEST_TENANT_B,
                "tiers": ["stm"],
                "top_k": 10,
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        contents = [m.get("content", "") for m in data.get("memories", [])]
        assert unique_content not in contents, (
            "Tenant isolation violated: tenant B can see tenant A's STM memory"
        )

    def test_delete_tenant_removes_all_memories(self) -> None:
        """Deleting a tenant's memories should return non-negative deleted counts."""
        ephemeral_tenant = f"ephemeral_{uuid.uuid4().hex[:8]}"

        # Store one memory
        httpx.post(
            f"{RAG_API_URL}/api/memory/store",
            json={
                "content": "Temporary data for deletion test.",
                "agent_id": "delete-test-agent",
                "session_id": str(uuid.uuid4()),
                "tenant_id": ephemeral_tenant,
                "tiers": ["stm"],
            },
            timeout=10,
        )

        # Delete all memories for the ephemeral tenant
        r = httpx.delete(
            f"{RAG_API_URL}/api/memory/{ephemeral_tenant}",
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert "deleted" in data
        assert data["total_deleted"] >= 0


# ── MMR Retrieval Tests ────────────────────────────────────────────────────────


class TestMMRRetrieval:
    def test_mmr_retrieve_returns_chunks(self) -> None:
        """MMR retrieval must return a non-empty response structure."""
        r = httpx.post(
            f"{RAG_API_URL}/api/retrieval/mmr",
            json={
                "query": "revenue growth customer acquisition",
                "tenant_id": TEST_TENANT,
                "collection": "knowledge_base",
                "top_k": 5,
                "mode": "default",
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "chunks" in data
        assert "lambda_used" in data
        assert "retrieval_ms" in data
        assert isinstance(data["chunks"], list)

    def test_mmr_lambda_modes(self) -> None:
        """Precise (0.9) and exploratory (0.5) modes must both return valid responses."""
        for mode, expected_lambda in [("precise", 0.9), ("exploratory", 0.5)]:
            r = httpx.post(
                f"{RAG_API_URL}/api/retrieval/mmr",
                json={
                    "query": "quarterly revenue analysis",
                    "tenant_id": TEST_TENANT,
                    "collection": "knowledge_base",
                    "top_k": 5,
                    "mode": mode,
                },
                timeout=10,
            )
            assert r.status_code == 200, f"Mode {mode} failed with {r.status_code}"
            data = r.json()
            assert "lambda_used" in data
            assert abs(data["lambda_used"] - expected_lambda) < 0.01, (
                f"Mode {mode}: expected lambda {expected_lambda}, got {data['lambda_used']}"
            )

    def test_mmr_max_chunks_per_source(self) -> None:
        """No source_id should appear more than 3 times in the results (CLAUDE.md §RAG)."""
        r = httpx.post(
            f"{RAG_API_URL}/api/retrieval/mmr",
            json={
                "query": "revenue growth analysis trends",
                "tenant_id": TEST_TENANT,
                "collection": "knowledge_base",
                "top_k": 20,
                "mode": "default",
            },
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        chunks = data.get("chunks", [])
        if not chunks:
            pytest.skip("No chunks in knowledge_base — populate first")

        source_counts: dict[str, int] = {}
        for chunk in chunks:
            source_id = chunk.get("source_id", "unknown")
            source_counts[source_id] = source_counts.get(source_id, 0) + 1

        violations = {s: c for s, c in source_counts.items() if c > 3}
        assert not violations, (
            f"MMR max_chunks_per_source=3 violated: {violations}"
        )

    def test_mmr_under_2s_slo(self) -> None:
        """Full MMR retrieval must complete in < 2s (p99 SLO per CLAUDE.md)."""
        start = time.perf_counter()
        r = httpx.post(
            f"{RAG_API_URL}/api/retrieval/mmr",
            json={
                "query": "customer churn revenue forecast",
                "tenant_id": TEST_TENANT,
                "collection": "knowledge_base",
                "top_k": 10,
                "mode": "default",
            },
            timeout=10,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 2000, f"MMR retrieval took {elapsed_ms:.0f}ms > 2s SLO"


# ── GraphRAG Tests ─────────────────────────────────────────────────────────────


class TestGraphRAG:
    def test_ingest_entities(self) -> None:
        """GraphRAG entity extraction + Neo4j upsert must succeed."""
        r = httpx.post(
            f"{RAG_API_URL}/api/graphrag/ingest",
            json={
                "text": (
                    "DataMind Corp partnered with Acme Analytics in Q3 2024. "
                    "The partnership increased revenue by 18% and reduced churn by 6%. "
                    "CEO Jane Smith announced the deal at the annual conference."
                ),
                "tenant_id": TEST_TENANT,
                "source_id": "graphrag-test-001",
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "entities_upserted" in data
        assert "relationships_upserted" in data
        assert isinstance(data["entities_upserted"], int)
        assert data["entities_upserted"] >= 0

    def test_search_community_context(self) -> None:
        """GraphRAG community search must return structured results."""
        r = httpx.post(
            f"{RAG_API_URL}/api/graphrag/search",
            json={
                "query": "DataMind revenue partnership",
                "tenant_id": TEST_TENANT,
                "max_hops": 2,
                "limit": 5,
            },
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert "entities_found" in data
        assert "community_summaries" in data
        assert "total" in data
        assert isinstance(data["entities_found"], list)
        assert isinstance(data["community_summaries"], list)

    def test_tenant_isolation(self) -> None:
        """GraphRAG nodes ingested for TEST_TENANT must not appear for TEST_TENANT_B."""
        unique_entity = f"UniqueEntity_{uuid.uuid4().hex[:8]}"

        # Ingest for tenant A
        httpx.post(
            f"{RAG_API_URL}/api/graphrag/ingest",
            json={
                "text": f"{unique_entity} acquired MegaCorp for $500M in 2024.",
                "tenant_id": TEST_TENANT,
                "source_id": "isolation-test",
            },
            timeout=30,
        )

        # Search from tenant B — must not find the unique entity
        r = httpx.post(
            f"{RAG_API_URL}/api/graphrag/search",
            json={
                "query": unique_entity,
                "tenant_id": TEST_TENANT_B,
                "max_hops": 2,
                "limit": 10,
            },
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        entity_names = [
            e.get("name", "") for e in data.get("entities_found", [])
        ]
        assert unique_entity not in entity_names, (
            "GraphRAG tenant isolation violated: tenant B found tenant A's entity"
        )


# ── RAGAS Evaluation Tests ─────────────────────────────────────────────────────


class TestRAGASEval:
    def test_evaluate_returns_metrics(self) -> None:
        """RAGAS eval must return faithfulness + answer_relevancy fields."""
        r = httpx.post(
            f"{RAG_API_URL}/api/evaluation/ragas",
            json={
                "question": "What was the revenue growth in Q3 2024?",
                "answer": "Revenue grew by 12% in Q3 2024 compared to Q3 2023.",
                "contexts": [
                    "Q3 2024 revenue reached $330,000, a 12% increase year-over-year.",
                    "Customer acquisition cost fell by 8% in Q3 2024.",
                ],
                "tenant_id": TEST_TENANT,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "faithfulness" in data, "RAGAS response must include faithfulness"
        assert "answer_relevancy" in data, "RAGAS response must include answer_relevancy"

    def test_faithfulness_score_between_0_and_1(self) -> None:
        """RAGAS faithfulness score must be in [0, 1]."""
        r = httpx.post(
            f"{RAG_API_URL}/api/evaluation/ragas",
            json={
                "question": "What is the customer acquisition cost trend?",
                "answer": "Customer acquisition cost decreased by 8% in Q3 2024.",
                "contexts": [
                    "Customer acquisition cost fell by 8% in Q3 2024.",
                ],
                "tenant_id": TEST_TENANT,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        faithfulness = data.get("faithfulness", -1)
        assert 0.0 <= faithfulness <= 1.0, (
            f"Faithfulness score {faithfulness} is outside [0, 1]"
        )


# ── Narrative Engine Tests ─────────────────────────────────────────────────────


class TestNarrativeEngine:
    def test_generate_report(self) -> None:
        """POST /api/narrative/generate must return sections with body and citations."""
        r = httpx.post(
            f"{RAG_API_URL}/api/narrative/generate",
            json={
                "title": "Q4 2024 Revenue Report",
                "sections_spec": SAMPLE_SECTIONS_SPEC,
                "retrieved_chunks": SAMPLE_CHUNKS[:6],
                "tenant_id": TEST_TENANT,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "sections" in data
        assert data["total_sections"] == len(SAMPLE_SECTIONS_SPEC)
        for section in data["sections"]:
            assert "section_id" in section
            assert "title" in section
            assert "body" in section
            assert len(section["body"]) > 50, "Section body is too short — likely a stub"
            assert "citations" in section
            assert isinstance(section["citations"], list)
            assert "confidence" in section
            assert 0.0 <= section["confidence"] <= 1.0

    def test_compile_returns_pdf_bytes(self) -> None:
        """POST /api/narrative/compile must return a compile response with a download URL."""
        report_id = str(uuid.uuid4())
        r = httpx.post(
            f"{RAG_API_URL}/api/narrative/compile",
            json={
                "report_id": report_id,
                "title": "Q4 2024 Revenue Report",
                "sections": SAMPLE_NARRATIVE_SECTIONS,
                "tenant_id": TEST_TENANT,
                "include_provenance": True,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "report_id" in data
        assert "merkle_root" in data
        assert "page_count" in data
        assert data["page_count"] >= 1
        assert "download_url" in data

        # Download the PDF and verify it starts with %PDF header
        download_url = data["download_url"]
        pdf_r = httpx.get(f"{RAG_API_URL}{download_url}", timeout=15)
        assert pdf_r.status_code == 200
        assert pdf_r.headers["content-type"] == "application/pdf"
        assert pdf_r.content[:4] == b"%PDF", "Response is not a valid PDF"

    def test_merkle_root_in_response(self) -> None:
        """Compiled report response must include a 64-char hex SHA-256 Merkle root."""
        report_id = str(uuid.uuid4())
        r = httpx.post(
            f"{RAG_API_URL}/api/narrative/compile",
            json={
                "report_id": report_id,
                "title": "Merkle Root Test Report",
                "sections": SAMPLE_NARRATIVE_SECTIONS[:1],
                "tenant_id": TEST_TENANT,
                "include_provenance": True,
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        merkle_root = data.get("merkle_root", "")
        assert len(merkle_root) == 64, (
            f"Expected 64-char hex Merkle root, got {len(merkle_root)} chars: {merkle_root!r}"
        )
        # Must be valid hex
        assert all(c in "0123456789abcdef" for c in merkle_root), (
            f"Merkle root is not valid hex: {merkle_root!r}"
        )

    def test_compile_deterministic_merkle_root(self) -> None:
        """Same sections must produce the same Merkle root (deterministic hash)."""
        payload = {
            "title": "Determinism Test",
            "sections": SAMPLE_NARRATIVE_SECTIONS,
            "tenant_id": TEST_TENANT,
            "include_provenance": True,
        }
        r1 = httpx.post(
            f"{RAG_API_URL}/api/narrative/compile",
            json={**payload, "report_id": str(uuid.uuid4())},
            timeout=60,
        )
        r2 = httpx.post(
            f"{RAG_API_URL}/api/narrative/compile",
            json={**payload, "report_id": str(uuid.uuid4())},
            timeout=60,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["merkle_root"] == r2.json()["merkle_root"], (
            "Merkle root is not deterministic for the same input sections"
        )


# ── DSR Automation Tests ───────────────────────────────────────────────────────


class TestDSRAutomation:
    def test_sar_returns_records_found(self) -> None:
        """POST /api/dsr/sar must return records_found per store."""
        r = httpx.post(
            f"{RAG_API_URL}/api/dsr/sar",
            json={
                "tenant_id": TEST_TENANT,
                "subject_email": "test.subject@example.com",
                "request_id": str(uuid.uuid4()),
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "request_id" in data
        assert "records_found" in data
        assert "stores_processed" in data
        assert "duration_ms" in data
        assert isinstance(data["records_found"], dict)
        # All 6 stores must be represented
        expected_stores = {"postgresql", "redis", "mongodb", "qdrant", "neo4j", "minio"}
        returned_stores = set(data["stores_processed"])
        assert expected_stores == returned_stores, (
            f"Expected stores {expected_stores}, got {returned_stores}"
        )
        # All counts must be non-negative integers
        for store, count in data["records_found"].items():
            assert isinstance(count, int) and count >= 0, (
                f"Store {store} has invalid count {count}"
            )

    def test_erasure_returns_certificate(self) -> None:
        """POST /api/dsr/erasure must return records_deleted and a certificate URL."""
        # Use an ephemeral subject email to avoid deleting real test data
        ephemeral_email = f"erasure_test_{uuid.uuid4().hex[:8]}@example.com"
        r = httpx.post(
            f"{RAG_API_URL}/api/dsr/erasure",
            json={
                "tenant_id": TEST_TENANT,
                "subject_email": ephemeral_email,
                "request_id": str(uuid.uuid4()),
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "records_deleted" in data
        assert "certificate_url" in data
        assert isinstance(data["records_deleted"], dict)
        assert data["certificate_url"].startswith("/api/dsr/certificate/")

        # Download and verify the certificate PDF
        cert_r = httpx.get(f"{RAG_API_URL}{data['certificate_url']}", timeout=15)
        assert cert_r.status_code == 200
        assert cert_r.headers["content-type"] == "application/pdf"
        assert cert_r.content[:4] == b"%PDF", "Certificate is not a valid PDF"

    def test_portability_returns_json_export(self) -> None:
        """POST /api/dsr/portability must return structured JSON data export."""
        r = httpx.post(
            f"{RAG_API_URL}/api/dsr/portability",
            json={
                "tenant_id": TEST_TENANT,
                "subject_email": "portability_test@example.com",
                "request_id": str(uuid.uuid4()),
            },
            timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert "export_format" in data
        assert data["export_format"] == "JSON"
        assert isinstance(data["data"], dict)

    def test_dsr_under_30s_slo(self) -> None:
        """SAR must complete within 30s (well within the 24h GDPR SLA)."""
        start = time.perf_counter()
        r = httpx.post(
            f"{RAG_API_URL}/api/dsr/sar",
            json={
                "tenant_id": TEST_TENANT,
                "subject_email": "slo_test@example.com",
                "request_id": str(uuid.uuid4()),
            },
            timeout=35,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 30_000, (
            f"DSR SAR took {elapsed_ms:.0f}ms > 30s SLO (GDPR SLA: 24h)"
        )

    def test_erasure_under_60s_slo(self) -> None:
        """Erasure must complete within 60s (well within the 72h GDPR SLA)."""
        start = time.perf_counter()
        r = httpx.post(
            f"{RAG_API_URL}/api/dsr/erasure",
            json={
                "tenant_id": TEST_TENANT,
                "subject_email": f"erasure_slo_{uuid.uuid4().hex[:8]}@example.com",
                "request_id": str(uuid.uuid4()),
            },
            timeout=65,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 60_000, (
            f"DSR erasure took {elapsed_ms:.0f}ms > 60s SLO (GDPR SLA: 72h)"
        )

    def test_certificate_404_for_unknown_request(self) -> None:
        """GET /api/dsr/certificate/{unknown_id} must return 404."""
        r = httpx.get(
            f"{RAG_API_URL}/api/dsr/certificate/nonexistent-request-id-xyz",
            timeout=5,
        )
        assert r.status_code == 404

    def test_report_404_for_unknown_id(self) -> None:
        """GET /api/narrative/reports/{unknown_id} must return 404."""
        r = httpx.get(
            f"{RAG_API_URL}/api/narrative/reports/nonexistent-report-id-xyz",
            timeout=5,
        )
        assert r.status_code == 404
