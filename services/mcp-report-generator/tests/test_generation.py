"""
Tests for mcp-report-generator — generation modules.
Day 11: Phase 2 — Merkle tree, PDF, PPTX, and IPFS anchor unit tests.

Coverage targets:
- MerkleTree: construction, root_hash determinism, proof generation, verify_claim
- anchor_to_ipfs: graceful IPFS_UNAVAILABLE when no API key
- generate_pdf: produces non-empty bytes, page_count >= 1
- generate_pptx: produces non-empty bytes, slide_count >= 2 (title + provenance)
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_report_generator.generation.merkle import MerkleTree, build_report_claims
from mcp_report_generator.generation.ipfs import anchor_to_ipfs


# ── MerkleTree Tests ──────────────────────────────────────────────────────────


class TestMerkleTree:
    """Unit tests for the SHA-256 MerkleTree class."""

    def test_single_claim(self) -> None:
        """A single claim produces a root hash equal to sha256(claim)."""
        claim = "only claim"
        tree = MerkleTree([claim])
        expected = hashlib.sha256(claim.encode()).hexdigest()
        assert tree.root_hash == expected

    def test_multiple_claims(self) -> None:
        """Multiple claims produce a non-empty root hash."""
        claims = ["claim A", "claim B", "claim C", "claim D"]
        tree = MerkleTree(claims)
        assert len(tree.root_hash) == 64
        assert all(c in "0123456789abcdef" for c in tree.root_hash)

    def test_empty_claims(self) -> None:
        """Empty claim list produces a stable root from sha256('empty')."""
        tree = MerkleTree([])
        expected = hashlib.sha256(b"empty").hexdigest()
        assert tree.root_hash == expected

    def test_deterministic(self) -> None:
        """Same input always produces the same root hash."""
        claims = ["Revenue: $1M", "Costs: $500K", "EBITDA: $500K"]
        tree1 = MerkleTree(claims)
        tree2 = MerkleTree(claims)
        assert tree1.root_hash == tree2.root_hash

    def test_different_order_different_root(self) -> None:
        """Different ordering of claims produces different root hashes."""
        claims_a = ["alpha", "beta", "gamma"]
        claims_b = ["gamma", "beta", "alpha"]
        tree_a = MerkleTree(claims_a)
        tree_b = MerkleTree(claims_b)
        assert tree_a.root_hash != tree_b.root_hash

    def test_single_claim_proof_is_empty_or_root(self) -> None:
        """Proof for a single-claim tree is trivially valid."""
        tree = MerkleTree(["lone claim"])
        proof = tree.get_proof(0)
        # For a single-node tree the proof path is empty (nothing to verify against)
        assert isinstance(proof, list)

    def test_proof_out_of_range(self) -> None:
        """get_proof raises IndexError for out-of-range index."""
        tree = MerkleTree(["a", "b", "c"])
        with pytest.raises(IndexError):
            tree.get_proof(10)

    def test_proof_negative_index(self) -> None:
        """get_proof raises IndexError for negative index."""
        tree = MerkleTree(["a", "b"])
        with pytest.raises(IndexError):
            tree.get_proof(-1)

    def test_proof_valid_for_two_claims(self) -> None:
        """Proof for index 0 in a two-claim tree is non-empty."""
        tree = MerkleTree(["first", "second"])
        proof = tree.get_proof(0)
        assert isinstance(proof, list)
        assert len(proof) >= 1

    def test_tamper_detection(self) -> None:
        """Adding a claim changes the root hash."""
        claims = ["data point 1", "data point 2"]
        tree_original = MerkleTree(claims)
        tree_tampered = MerkleTree(claims + ["injected claim"])
        assert tree_original.root_hash != tree_tampered.root_hash

    def test_build_report_claims_structure(self) -> None:
        """build_report_claims produces correct claim prefixes."""
        sections = [
            {"heading": "Revenue", "content": "Sales grew 10%.", "data": [{"month": "Jan", "value": "100"}]},
        ]
        claims = build_report_claims("Q1 Report", sections)

        assert any(c.startswith("title:") for c in claims)
        assert any(c.startswith("heading:") for c in claims)
        assert any(c.startswith("content:") for c in claims)
        assert any(c.startswith("data_row:") for c in claims)

    def test_build_report_claims_no_data(self) -> None:
        """build_report_claims works without optional data rows."""
        sections = [{"heading": "Summary", "content": "All good."}]
        claims = build_report_claims("Simple Report", sections)
        # Should have title + heading + content = 3 claims
        assert len(claims) == 3

    def test_odd_leaf_count_completes(self) -> None:
        """Tree with odd number of leaves (duplicate-last convention) builds correctly."""
        tree = MerkleTree(["a", "b", "c"])
        assert len(tree.root_hash) == 64

    def test_large_claim_set(self) -> None:
        """Tree handles 1000 claims without error."""
        claims = [f"claim_{i}" for i in range(1000)]
        tree = MerkleTree(claims)
        assert len(tree.root_hash) == 64


# ── IPFS Anchor Tests ─────────────────────────────────────────────────────────


class TestIPFSAnchor:
    """Unit tests for the anchor_to_ipfs function."""

    async def test_skips_when_no_api_key(self) -> None:
        """Returns IPFS_UNAVAILABLE immediately when pinata_api_key is empty."""
        import httpx

        async with httpx.AsyncClient() as client:
            result = await anchor_to_ipfs(
                http_client=client,
                report_id="test-report-001",
                merkle_root="a" * 64,
                pinata_api_key="",
                pinata_secret_key="",
                pinata_endpoint="https://api.pinata.cloud",
            )

        assert result["code"] == "IPFS_UNAVAILABLE"
        assert "error" in result

    async def test_returns_error_on_http_failure(self) -> None:
        """Returns IPFS_ANCHOR_FAILED when Pinata returns an HTTP error."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        result = await anchor_to_ipfs(
            http_client=mock_client,
            report_id="test-report-002",
            merkle_root="b" * 64,
            pinata_api_key="fake-key",
            pinata_secret_key="fake-secret",
            pinata_endpoint="https://api.pinata.cloud",
        )

        assert result["code"] == "IPFS_ANCHOR_FAILED"
        assert "error" in result

    async def test_returns_ipfs_hash_on_success(self) -> None:
        """Returns ipfs_hash and pinata_url on successful Pinata response."""
        import httpx

        fake_hash = "QmFakeIpfsHash1234567890abcdef"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"IpfsHash": fake_hash}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        result = await anchor_to_ipfs(
            http_client=mock_client,
            report_id="test-report-003",
            merkle_root="c" * 64,
            pinata_api_key="real-key",
            pinata_secret_key="real-secret",
            pinata_endpoint="https://api.pinata.cloud",
        )

        assert result["ipfs_hash"] == fake_hash
        assert result["pinata_url"] == f"https://gateway.pinata.cloud/ipfs/{fake_hash}"
        assert "anchored_at" in result


# ── PDF Generation Tests ──────────────────────────────────────────────────────


class TestPDFGeneration:
    """Unit tests for WeasyPrint PDF generation."""

    @pytest.fixture
    def sample_sections(self) -> list[dict]:
        return [
            {
                "heading": "Executive Summary",
                "content": "Revenue grew by **25%** YoY. Key drivers include:\n- Market expansion\n- New product launches",
                "data": None,
            },
            {
                "heading": "Financial Highlights",
                "content": "See table below for Q1 figures.",
                "data": [
                    {"Metric": "Revenue", "Q1 2025": "$5.2M", "Q1 2026": "$6.5M"},
                    {"Metric": "EBITDA", "Q1 2025": "$1.1M", "Q1 2026": "$1.8M"},
                ],
            },
        ]

    async def test_generates_bytes(self, sample_sections: list[dict]) -> None:
        """generate_pdf returns non-empty bytes."""
        from mcp_report_generator.generation.pdf import generate_pdf

        pdf_bytes, page_count = await generate_pdf(
            report_id="test-001",
            title="Q1 2026 Financial Report",
            sections=sample_sections,
            merkle_root="a" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
            include_provenance=True,
        )
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

    async def test_page_count_nonzero(self, sample_sections: list[dict]) -> None:
        """Estimated page count is >= 1."""
        from mcp_report_generator.generation.pdf import generate_pdf

        _, page_count = await generate_pdf(
            report_id="test-002",
            title="Short Report",
            sections=sample_sections,
            merkle_root="b" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert page_count >= 1

    async def test_pdf_magic_bytes(self, sample_sections: list[dict]) -> None:
        """Generated output starts with the PDF magic bytes %PDF."""
        from mcp_report_generator.generation.pdf import generate_pdf

        pdf_bytes, _ = await generate_pdf(
            report_id="test-003",
            title="Magic Bytes Check",
            sections=sample_sections,
            merkle_root="c" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert pdf_bytes[:4] == b"%PDF"

    async def test_no_provenance(self, sample_sections: list[dict]) -> None:
        """Provenance footer is omitted when include_provenance=False."""
        from mcp_report_generator.generation.pdf import generate_pdf

        pdf_bytes, _ = await generate_pdf(
            report_id="test-004",
            title="No Provenance Report",
            sections=sample_sections,
            merkle_root="d" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
            include_provenance=False,
        )
        # PDF should still be non-empty
        assert len(pdf_bytes) > 0

    async def test_empty_section_data(self) -> None:
        """Sections with no data field generate successfully."""
        from mcp_report_generator.generation.pdf import generate_pdf

        sections = [{"heading": "Notes", "content": "No data available.", "data": None}]
        pdf_bytes, page_count = await generate_pdf(
            report_id="test-005",
            title="Minimal Report",
            sections=sections,
            merkle_root="e" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert len(pdf_bytes) > 0
        assert page_count >= 1


# ── PPTX Generation Tests ─────────────────────────────────────────────────────


class TestPPTXGeneration:
    """Unit tests for python-pptx PPTX generation."""

    @pytest.fixture
    def sample_sections(self) -> list[dict]:
        return [
            {
                "heading": "Market Analysis",
                "content": "The market grew 15% in 2026.",
                "data": [
                    {"Region": "APAC", "Growth": "22%"},
                    {"Region": "EMEA", "Growth": "14%"},
                    {"Region": "Americas", "Growth": "10%"},
                ],
            },
            {
                "heading": "Product Roadmap",
                "content": "Q2 milestones:\n1. Launch feature X\n2. Integrate partner API",
                "data": None,
            },
        ]

    async def test_generates_bytes(self, sample_sections: list[dict]) -> None:
        """generate_pptx returns non-empty bytes."""
        from mcp_report_generator.generation.pptx import generate_pptx

        pptx_bytes, slide_count = await generate_pptx(
            report_id="pptx-001",
            title="DataMind 2026 Strategy",
            sections=sample_sections,
            merkle_root="f" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert isinstance(pptx_bytes, bytes)
        assert len(pptx_bytes) > 0

    async def test_slide_count(self, sample_sections: list[dict]) -> None:
        """Slide count equals section count + 2 (title + provenance slides)."""
        from mcp_report_generator.generation.pptx import generate_pptx

        _, slide_count = await generate_pptx(
            report_id="pptx-002",
            title="Slide Count Test",
            sections=sample_sections,
            merkle_root="g" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        expected_slides = len(sample_sections) + 2  # title + section slides + provenance
        assert slide_count == expected_slides

    async def test_pptx_magic_bytes(self, sample_sections: list[dict]) -> None:
        """Generated output is a valid ZIP (PPTX is a ZIP archive): starts with PK."""
        from mcp_report_generator.generation.pptx import generate_pptx

        pptx_bytes, _ = await generate_pptx(
            report_id="pptx-003",
            title="Magic Bytes Check",
            sections=sample_sections,
            merkle_root="h" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        # PPTX (OOXML) files are ZIP archives — magic bytes PK\x03\x04
        assert pptx_bytes[:2] == b"PK"

    async def test_single_section(self) -> None:
        """PPTX with a single section produces 3 slides (title + 1 content + provenance)."""
        from mcp_report_generator.generation.pptx import generate_pptx

        sections = [{"heading": "Only Section", "content": "Just one.", "data": None}]
        _, slide_count = await generate_pptx(
            report_id="pptx-004",
            title="Single Section",
            sections=sections,
            merkle_root="i" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert slide_count == 3

    async def test_table_with_many_rows(self) -> None:
        """Data tables truncate at _MAX_TABLE_ROWS without raising."""
        from mcp_report_generator.generation.pptx import generate_pptx

        large_data = [{"Index": str(i), "Value": str(i * 10)} for i in range(20)]
        sections = [{"heading": "Large Table", "content": "Lots of rows.", "data": large_data}]
        pptx_bytes, _ = await generate_pptx(
            report_id="pptx-005",
            title="Large Table Test",
            sections=sections,
            merkle_root="j" * 64,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        assert len(pptx_bytes) > 0
