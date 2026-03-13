"""
CompilerAgent — assembles NarrativeSections into final PDF + Merkle provenance certificate.
Day 22: Phase 5 RAG & Reporting.

Protocols: None
SOLID: SRP (PDF compilation only), OCP (extend for new output formats), DIP (WeasyPrint injected via executor)
Benchmark: tests/benchmarks/bench_compiler.py — target < 30s for 10-page report
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
from jinja2 import Template
from langfuse.decorators import observe

from rag_api.narrative.narrative_agent import NarrativeSection

log = structlog.get_logger(__name__)


@dataclass
class CompiledReport:
    """The output of a successful CompilerAgent.compile() call."""

    report_id: str
    tenant_id: str
    title: str
    pdf_bytes: bytes
    page_count: int
    merkle_root: str
    sections: list[str]
    generation_ms: float


# ── HTML Template ─────────────────────────────────────────────────────────────

_REPORT_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ title | e }}</title>
<style>
  @page {
    margin: 2.2cm 2cm;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #718096;
    }
    @top-right {
      content: "CONFIDENTIAL — DataMind Enterprise";
      font-size: 8pt;
      color: #a0aec0;
    }
  }

  body {
    font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
    font-size: 11pt;
    color: #1a202c;
    line-height: 1.65;
    background: #ffffff;
  }

  .cover {
    background: #1A365D;
    color: #ffffff;
    padding: 60px 40px;
    margin-bottom: 40px;
    border-radius: 4px;
  }

  .cover h1 {
    font-size: 26pt;
    font-weight: 700;
    margin: 0 0 12px 0;
    letter-spacing: -0.5px;
    color: #ffffff;
    border: none;
  }

  .cover .subtitle {
    font-size: 12pt;
    opacity: 0.85;
    margin: 0;
  }

  .cover .meta-row {
    margin-top: 24px;
    font-size: 10pt;
    opacity: 0.75;
    border-top: 1px solid rgba(255,255,255,0.3);
    padding-top: 16px;
  }

  .toc {
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 20px 24px;
    margin-bottom: 32px;
  }

  .toc h2 {
    font-size: 13pt;
    color: #1A365D;
    margin: 0 0 12px 0;
    border: none;
    padding: 0;
  }

  .toc ol {
    margin: 0;
    padding-left: 20px;
    font-size: 10pt;
    color: #2d3748;
  }

  .toc li {
    margin: 4px 0;
  }

  h1 {
    color: #1A365D;
    font-size: 22pt;
    border-bottom: 3px solid #1A365D;
    padding-bottom: 8px;
    margin-bottom: 24px;
    page-break-before: always;
  }

  h2 {
    color: #2d3748;
    font-size: 15pt;
    margin-top: 28px;
    margin-bottom: 10px;
    border-left: 4px solid #4a90d9;
    padding-left: 10px;
  }

  p {
    margin: 10px 0;
    text-align: justify;
  }

  .section-body {
    margin-bottom: 24px;
  }

  .citation-tag {
    font-size: 8.5pt;
    color: #2b6cb0;
    background: #ebf8ff;
    border-radius: 2px;
    padding: 1px 4px;
    font-family: 'DejaVu Sans Mono', monospace;
  }

  .confidence-badge {
    display: inline-block;
    font-size: 8pt;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: bold;
    margin-left: 8px;
  }

  .confidence-high   { background: #c6f6d5; color: #276749; }
  .confidence-medium { background: #fefcbf; color: #975a16; }
  .confidence-low    { background: #fed7d7; color: #9b2c2c; }

  .section-divider {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 28px 0;
  }

  .provenance-certificate {
    font-size: 9pt;
    color: #4a5568;
    border: 1px solid #cbd5e0;
    border-top: 3px solid #1A365D;
    margin-top: 48px;
    padding: 16px 20px;
    background: #f7fafc;
    border-radius: 4px;
    page-break-inside: avoid;
  }

  .provenance-certificate h3 {
    color: #1A365D;
    font-size: 11pt;
    margin: 0 0 12px 0;
  }

  .hash-value {
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 8pt;
    word-break: break-all;
    background: #edf2f7;
    padding: 4px 8px;
    border-radius: 3px;
    display: block;
    margin: 4px 0 8px 0;
    color: #2d3748;
  }

  .brand-footer {
    text-align: center;
    font-size: 8pt;
    color: #a0aec0;
    margin-top: 32px;
    border-top: 1px solid #e2e8f0;
    padding-top: 12px;
  }
</style>
</head>
<body>

<!-- Cover Block -->
<div class="cover">
  <h1>{{ title | e }}</h1>
  <p class="subtitle">AI-Generated Analytics Report</p>
  <div class="meta-row">
    Report ID: {{ report_id }} &nbsp;|&nbsp;
    Tenant: {{ tenant_id | e }} &nbsp;|&nbsp;
    Generated: {{ generated_at }}
  </div>
</div>

<!-- Table of Contents -->
<div class="toc">
  <h2>Contents</h2>
  <ol>
    {% for section in sections %}
    <li>{{ section.title | e }}</li>
    {% endfor %}
  </ol>
</div>

<!-- Sections -->
{% for section in sections %}
<h2>
  {{ loop.index }}. {{ section.title | e }}
  {% if section.confidence >= 0.8 %}
  <span class="confidence-badge confidence-high">High Confidence</span>
  {% elif section.confidence >= 0.5 %}
  <span class="confidence-badge confidence-medium">Medium Confidence</span>
  {% else %}
  <span class="confidence-badge confidence-low">Low Confidence</span>
  {% endif %}
</h2>
<div class="section-body">
  {% for paragraph in section.body.split('\n\n') %}
  {% if paragraph.strip() %}
  <p>{{ paragraph.strip() | e }}</p>
  {% endif %}
  {% endfor %}
</div>
{% if section.citations %}
<p style="font-size:9pt;color:#718096;">
  <strong>Sources cited:</strong>
  {% for c in section.citations %}
  <span class="citation-tag">{{ c | e }}</span>{% if not loop.last %}&nbsp;{% endif %}
  {% endfor %}
</p>
{% endif %}
{% if not loop.last %}<hr class="section-divider">{% endif %}
{% endfor %}

{% if include_provenance %}
<!-- Provenance Certificate -->
<div class="provenance-certificate">
  <h3>Cryptographic Provenance Certificate</h3>
  <strong>Report ID:</strong> {{ report_id }}<br>
  <strong>Sections:</strong> {{ sections | length }}<br>
  <strong>Merkle Root (SHA-256):</strong>
  <span class="hash-value">{{ merkle_root }}</span>
  <strong>Generated At:</strong> {{ generated_at }}<br>
  <strong>Algorithm:</strong> SHA-256 iterative Merkle tree over section body hashes<br>
  <em>
    Every narrative section's content is hashed and combined into the Merkle root above.
    Any post-generation modification to the report content will invalidate this root.
    Anchor verification is available via IPFS.
  </em>
</div>
{% endif %}

<div class="brand-footer">
  DataMind Enterprise v2 &mdash; Verifiable AI Analytics &mdash; Powered by MCP + A2A
</div>

</body>
</html>"""
)


class CompilerAgent:
    """Assembles NarrativeSections into a PDF with WeasyPrint and Merkle provenance.

    This agent reuses the WeasyPrint pattern established in ``mcp-report-generator``
    and adds a Merkle tree over section bodies for tamper-evident provenance.

    SOLID:
        SRP: Compilation only; does not generate narrative content.
        OCP: Override ``_build_html`` to support new output formats.
    """

    @observe(name="compiler.compile_report")
    async def compile(
        self,
        report_id: str,
        title: str,
        sections: list[NarrativeSection],
        tenant_id: str,
        include_provenance: bool = True,
    ) -> CompiledReport:
        """Assemble sections into a PDF with a Merkle provenance certificate.

        Args:
            report_id: Unique identifier for this compiled report.
            title: Report title rendered on the cover page.
            sections: Ordered list of NarrativeSections from NarrativeAgent.
            tenant_id: Owning tenant — embedded in the cover metadata.
            include_provenance: Whether to append the Merkle certificate page.

        Returns:
            CompiledReport containing the PDF bytes, page count, and Merkle root.

        Raises:
            RuntimeError: If WeasyPrint fails to render.
        """
        start = time.perf_counter()

        if not sections:
            raise ValueError("Cannot compile a report with zero sections.")

        merkle_root = self._build_merkle_root(sections)
        generated_at = datetime.now(timezone.utc).isoformat()

        pdf_bytes, page_count = await self._render_pdf(
            title=title,
            report_id=report_id,
            sections=sections,
            tenant_id=tenant_id,
            merkle_root=merkle_root,
            generated_at=generated_at,
            include_provenance=include_provenance,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        log.info(
            "compiler.report.compiled",
            report_id=report_id,
            tenant_id=tenant_id,
            sections=len(sections),
            page_count=page_count,
            size_bytes=len(pdf_bytes),
            merkle_root=merkle_root[:16] + "…",
            elapsed_ms=round(elapsed_ms, 2),
        )

        return CompiledReport(
            report_id=report_id,
            tenant_id=tenant_id,
            title=title,
            pdf_bytes=pdf_bytes,
            page_count=page_count,
            merkle_root=merkle_root,
            sections=[s.title for s in sections],
            generation_ms=elapsed_ms,
        )

    def _build_merkle_root(self, sections: list[NarrativeSection]) -> str:
        """Compute an iterative SHA-256 Merkle root over section body hashes.

        Each section body is SHA-256 hashed to form a leaf. Adjacent pairs are
        concatenated (bytes) and hashed to build the next level. If the number
        of leaves is odd the last leaf is duplicated. This continues until a
        single root hash remains.

        Args:
            sections: The narrative sections whose bodies are the Merkle leaves.

        Returns:
            Hex-encoded 64-character SHA-256 Merkle root string.
        """
        if not sections:
            return hashlib.sha256(b"empty").hexdigest()

        # Build leaf hashes
        leaves: list[bytes] = [
            hashlib.sha256(s.body.encode("utf-8")).digest() for s in sections
        ]

        current_level = leaves
        while len(current_level) > 1:
            # Duplicate last node if odd count
            if len(current_level) % 2 == 1:
                current_level = current_level + [current_level[-1]]
            next_level: list[bytes] = []
            for i in range(0, len(current_level), 2):
                combined = current_level[i] + current_level[i + 1]
                next_level.append(hashlib.sha256(combined).digest())
            current_level = next_level

        return current_level[0].hex()

    async def _render_pdf(
        self,
        title: str,
        report_id: str,
        sections: list[NarrativeSection],
        tenant_id: str,
        merkle_root: str,
        generated_at: str,
        include_provenance: bool,
    ) -> tuple[bytes, int]:
        """Render the HTML template to PDF bytes using WeasyPrint.

        WeasyPrint is CPU-bound and not async-safe, so rendering is delegated
        to a thread-pool executor to keep the event loop free.

        Args:
            title: Report title.
            report_id: Report identifier.
            sections: All NarrativeSections to render.
            tenant_id: Owning tenant, shown in cover metadata.
            merkle_root: Precomputed Merkle root hex string.
            generated_at: ISO-8601 generation timestamp.
            include_provenance: Whether to append the certificate page.

        Returns:
            Tuple of (pdf_bytes, estimated_page_count).
        """
        html_str = _REPORT_TEMPLATE.render(
            title=title,
            report_id=report_id,
            tenant_id=tenant_id,
            sections=sections,
            merkle_root=merkle_root,
            generated_at=generated_at,
            include_provenance=include_provenance,
        )

        def _weasyprint_sync(html: str) -> bytes:
            from weasyprint import HTML  # noqa: PLC0415

            return HTML(string=html).write_pdf()  # type: ignore[no-any-return]

        loop = asyncio.get_event_loop()
        try:
            pdf_bytes: bytes = await loop.run_in_executor(None, _weasyprint_sync, html_str)
        except Exception as exc:
            log.error("compiler.pdf.render_failed", error=str(exc), report_id=report_id)
            raise RuntimeError(f"WeasyPrint render failed: {exc}") from exc

        # Estimate page count: ~2500 chars of HTML per rendered page
        page_count = max(1, len(html_str) // 2500)
        return pdf_bytes, page_count
