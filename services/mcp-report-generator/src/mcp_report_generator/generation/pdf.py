"""
MCP Report Generator — WeasyPrint PDF generation.
Day 11: Phase 2 — Jinja2 HTML template → WeasyPrint PDF with provenance footer.

Protocols: None (internal utility called by main.py MCP tool)
SOLID: SRP (PDF generation only), OCP (extend PDFGenerator for new templates)
Benchmark: tests/benchmarks/bench_report.py — target < 5s for 10-page report
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import markdown as md
import structlog
from jinja2 import Template

log = structlog.get_logger(__name__)

# ── Jinja2 HTML Template ──────────────────────────────────────────────────────

_PDF_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
  @page {
    margin: 2cm;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #718096;
    }
  }

  body {
    font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
    font-size: 11pt;
    color: #222222;
    line-height: 1.6;
  }

  h1 {
    color: #1a365d;
    font-size: 22pt;
    border-bottom: 3px solid #1a365d;
    padding-bottom: 8px;
    margin-bottom: 24px;
  }

  h2 {
    color: #2d3748;
    font-size: 15pt;
    margin-top: 28px;
    margin-bottom: 10px;
    border-left: 4px solid #4a90d9;
    padding-left: 10px;
  }

  h3 {
    color: #4a5568;
    font-size: 12pt;
    margin-top: 16px;
  }

  p {
    margin: 8px 0;
  }

  ul, ol {
    margin: 8px 0;
    padding-left: 24px;
  }

  code {
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 3px;
    padding: 1px 5px;
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 10pt;
  }

  pre {
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 12px;
    overflow-x: auto;
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 9pt;
    line-height: 1.4;
  }

  table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 10pt;
  }

  th {
    background-color: #1a365d;
    color: #ffffff;
    padding: 9px 12px;
    text-align: left;
    font-weight: bold;
  }

  td {
    border: 1px solid #e2e8f0;
    padding: 7px 12px;
    vertical-align: top;
  }

  tr:nth-child(even) td {
    background-color: #f7fafc;
  }

  tr:hover td {
    background-color: #ebf4ff;
  }

  blockquote {
    border-left: 4px solid #4a90d9;
    margin: 12px 0;
    padding: 8px 16px;
    background: #ebf8ff;
    color: #2b6cb0;
    font-style: italic;
  }

  .report-meta {
    color: #718096;
    font-size: 10pt;
    margin-bottom: 24px;
  }

  .section-divider {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 24px 0;
  }

  .provenance-certificate {
    font-size: 9pt;
    color: #718096;
    border-top: 2px solid #e2e8f0;
    margin-top: 40px;
    padding-top: 12px;
    background: #f7fafc;
    padding: 12px 16px;
    border-radius: 4px;
  }

  .provenance-certificate strong {
    color: #4a5568;
    font-size: 10pt;
  }

  .provenance-hash {
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 8pt;
    word-break: break-all;
    color: #4a5568;
    background: #edf2f7;
    padding: 4px 8px;
    border-radius: 3px;
    display: block;
    margin: 4px 0;
  }

  .datamind-badge {
    color: #1a365d;
    font-weight: bold;
    font-size: 10pt;
  }
</style>
</head>
<body>

<h1>{{ title }}</h1>
<div class="report-meta">
  <span class="datamind-badge">DataMind Enterprise</span> &nbsp;|&nbsp;
  Report ID: {{ report_id }} &nbsp;|&nbsp;
  Generated: {{ generated_at }}
</div>

{% for section in sections %}
<h2>{{ section.heading | e }}</h2>
<div class="content">{{ section.content_html | safe }}</div>

{% if section.data and section.data | length > 0 %}
<table>
  <thead>
    <tr>
      {% for col in section.data[0].keys() %}
      <th>{{ col | e }}</th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for row in section.data %}
    <tr>
      {% for val in row.values() %}
      <td>{{ val | e }}</td>
      {% endfor %}
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}

{% if not loop.last %}
<hr class="section-divider">
{% endif %}
{% endfor %}

{% if include_provenance %}
<div class="provenance-certificate">
  <strong>Provenance Certificate</strong><br><br>
  <strong>Report ID:</strong> {{ report_id }}<br>
  <strong>Merkle Root (SHA-256):</strong>
  <span class="provenance-hash">{{ merkle_root }}</span>
  <strong>Generated At:</strong> {{ generated_at }}<br>
  <strong>Platform:</strong> DataMind Enterprise v2 — Verifiable AI Analytics<br>
  <em>This report's content integrity is cryptographically guaranteed by the
  Merkle root above. Anchor verification available via IPFS.</em>
</div>
{% endif %}

</body>
</html>
"""

_TEMPLATE: Template = Template(_PDF_TEMPLATE)


async def generate_pdf(
    report_id: str,
    title: str,
    sections: list[dict[str, Any]],
    merkle_root: str,
    generated_at: str,
    include_provenance: bool = True,
) -> tuple[bytes, int]:
    """Generate a PDF document from structured report sections.

    Converts each section's Markdown content to HTML via the `markdown`
    library, renders the full HTML using Jinja2, then passes the result to
    WeasyPrint running in a thread-pool executor (WeasyPrint is CPU-bound
    and not async-safe).

    Args:
        report_id: Unique report identifier embedded in metadata.
        title: Report title rendered as H1.
        sections: List of section dicts with keys: heading (str), content (str),
            data (list[dict] | None).
        merkle_root: SHA-256 Merkle root to embed in the provenance footer.
        generated_at: ISO-8601 UTC timestamp string.
        include_provenance: Whether to render the provenance certificate footer.

    Returns:
        Tuple of (pdf_bytes, estimated_page_count). Page count is estimated as
        max(1, len(html) // 2500) — sufficient for SLO monitoring; WeasyPrint
        does not expose a page-count API without full rendering to PDF.

    Raises:
        RuntimeError: If WeasyPrint fails to render the document.
    """
    start = time.perf_counter()

    # Convert Markdown to HTML for each section
    processed_sections: list[dict[str, Any]] = []
    for section in sections:
        content_html = md.markdown(
            section.get("content", ""),
            extensions=["tables", "fenced_code", "nl2br"],
        )
        processed_sections.append(
            {
                **section,
                "content_html": content_html,
            }
        )

    html_str = _TEMPLATE.render(
        title=title,
        report_id=report_id,
        sections=processed_sections,
        include_provenance=include_provenance,
        merkle_root=merkle_root,
        generated_at=generated_at,
    )

    # WeasyPrint is CPU-bound — run in thread-pool to keep event loop free
    loop = asyncio.get_event_loop()

    def _render() -> bytes:
        # Import inside executor to isolate WeasyPrint's Pango/Cairo globals
        from weasyprint import HTML  # noqa: PLC0415

        return HTML(string=html_str).write_pdf()  # type: ignore[no-any-return]

    try:
        pdf_bytes: bytes = await loop.run_in_executor(None, _render)
    except Exception as exc:
        log.error("pdf.render.failed", error=str(exc), report_id=report_id)
        raise RuntimeError(f"WeasyPrint PDF render failed: {exc}") from exc

    elapsed_ms = (time.perf_counter() - start) * 1000
    # Estimate page count: roughly 2500 characters of HTML per rendered page
    page_count = max(1, len(html_str) // 2500)

    log.info(
        "pdf.generated",
        report_id=report_id,
        size_bytes=len(pdf_bytes),
        page_count=page_count,
        elapsed_ms=round(elapsed_ms, 2),
    )

    return pdf_bytes, page_count
