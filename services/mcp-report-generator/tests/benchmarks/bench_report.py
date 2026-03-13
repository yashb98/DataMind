"""
Benchmark: Report generation latency.
Day 11: Phase 2 — SLO targets: PDF < 5s p99, PPTX < 2s p99.

Run with:
    pytest tests/benchmarks/bench_report.py -v --benchmark-sort=mean

Results are logged to ClickHouse analytics.benchmarks table in production.
"""

from __future__ import annotations

from datetime import datetime, timezone


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_sections(n: int = 5) -> list[dict]:
    """Create n realistic report sections for benchmarking."""
    sections = []
    for i in range(n):
        sections.append(
            {
                "heading": f"Section {i + 1}: Analysis Findings",
                "content": (
                    f"## Key Finding {i + 1}\n\n"
                    "Revenue for the period increased by **12.5%** year-over-year, "
                    "driven primarily by:\n\n"
                    "- Expansion into APAC markets (+22% growth)\n"
                    "- New enterprise contracts signed in Q3\n"
                    "- Improved customer retention (NPS: 72 → 84)\n\n"
                    "Risk factors include macroeconomic headwinds and FX volatility."
                ),
                "data": [
                    {"Metric": "Revenue", "Previous": "$4.2M", "Current": "$4.7M", "Delta": "+12.5%"},
                    {"Metric": "Gross Margin", "Previous": "68%", "Current": "71%", "Delta": "+3pp"},
                    {"Metric": "EBITDA", "Previous": "$0.9M", "Current": "$1.2M", "Delta": "+33%"},
                    {"Metric": "Headcount", "Previous": "48", "Current": "55", "Delta": "+7"},
                ],
            }
        )
    return sections


_REPORT_ID = "bench-report-001"
_MERKLE_ROOT = "a" * 64
_GENERATED_AT = datetime.now(timezone.utc).isoformat()
_TITLE = "DataMind Enterprise — Q1 2026 Benchmark Report"


# ── Merkle Tree Benchmarks ────────────────────────────────────────────────────


def test_merkle_tree_perf(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: MerkleTree construction from 50 claims.

    SLO: < 5ms p99 (pure Python, no I/O).
    """
    from mcp_report_generator.generation.merkle import MerkleTree, build_report_claims

    sections = _make_sections(10)
    claims = build_report_claims(_TITLE, sections)
    # ~50 claims for a 10-section report

    def run() -> str:
        return MerkleTree(claims).root_hash

    root = benchmark(run)
    assert len(root) == 64
    # Sanity: all hex chars
    assert all(c in "0123456789abcdef" for c in root)


def test_merkle_tree_large_perf(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: MerkleTree with 1000 claims.

    SLO: < 50ms p99.
    """
    from mcp_report_generator.generation.merkle import MerkleTree

    claims = [f"claim number {i}: some long claim text for section analysis" for i in range(1000)]

    def run() -> str:
        return MerkleTree(claims).root_hash

    root = benchmark(run)
    assert len(root) == 64


def test_build_report_claims_perf(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: build_report_claims for 10 sections with data rows.

    SLO: < 1ms p99.
    """
    from mcp_report_generator.generation.merkle import build_report_claims

    sections = _make_sections(10)

    def run() -> list[str]:
        return build_report_claims(_TITLE, sections)

    result = benchmark(run)
    assert len(result) > 0


# ── PPTX Generation Benchmarks ────────────────────────────────────────────────


def test_pptx_generation_perf(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: PPTX generation for 5-section report.

    SLO: < 2s p99 (target: typically < 500ms in practice).
    """
    import asyncio

    from mcp_report_generator.generation.pptx import generate_pptx

    sections = _make_sections(5)

    def run() -> tuple[bytes, int]:
        return asyncio.get_event_loop().run_until_complete(
            generate_pptx(
                report_id=_REPORT_ID,
                title=_TITLE,
                sections=sections,
                merkle_root=_MERKLE_ROOT,
                generated_at=_GENERATED_AT,
            )
        )

    pptx_bytes, slide_count = benchmark(run)
    assert len(pptx_bytes) > 0
    assert slide_count == 7  # title + 5 content + provenance


def test_pptx_generation_10_sections(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: PPTX generation for 10-section report.

    SLO: < 2s p99.
    """
    import asyncio

    from mcp_report_generator.generation.pptx import generate_pptx

    sections = _make_sections(10)

    def run() -> tuple[bytes, int]:
        return asyncio.get_event_loop().run_until_complete(
            generate_pptx(
                report_id=_REPORT_ID,
                title=_TITLE,
                sections=sections,
                merkle_root=_MERKLE_ROOT,
                generated_at=_GENERATED_AT,
            )
        )

    pptx_bytes, slide_count = benchmark(run)
    assert len(pptx_bytes) > 0
    assert slide_count == 12  # title + 10 content + provenance


# ── PDF Generation Benchmarks ─────────────────────────────────────────────────


def test_pdf_generation_perf(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: PDF generation for 5-section report.

    SLO: < 5s p99 (WeasyPrint is slower due to CSS layout engine).
    """
    import asyncio

    from mcp_report_generator.generation.pdf import generate_pdf

    sections = _make_sections(5)

    def run() -> tuple[bytes, int]:
        return asyncio.get_event_loop().run_until_complete(
            generate_pdf(
                report_id=_REPORT_ID,
                title=_TITLE,
                sections=sections,
                merkle_root=_MERKLE_ROOT,
                generated_at=_GENERATED_AT,
                include_provenance=True,
            )
        )

    pdf_bytes, page_count = benchmark(run)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:4] == b"%PDF"
    assert page_count >= 1


def test_pdf_generation_10_sections(benchmark) -> None:  # type: ignore[type-arg]
    """Benchmark: PDF generation for 10-section report (approx 10 pages).

    SLO: < 5s p99.
    """
    import asyncio

    from mcp_report_generator.generation.pdf import generate_pdf

    sections = _make_sections(10)

    def run() -> tuple[bytes, int]:
        return asyncio.get_event_loop().run_until_complete(
            generate_pdf(
                report_id=_REPORT_ID,
                title=_TITLE,
                sections=sections,
                merkle_root=_MERKLE_ROOT,
                generated_at=_GENERATED_AT,
                include_provenance=True,
            )
        )

    pdf_bytes, page_count = benchmark(run)
    assert len(pdf_bytes) > 0
    assert page_count >= 1
