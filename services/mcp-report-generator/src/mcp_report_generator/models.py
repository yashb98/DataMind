"""
MCP Report Generator — Request / response Pydantic models.
Day 11: Phase 2 — Structured I/O for generate_report and anchor_ipfs tools.

Protocols: MCP (JSON-RPC 2.0)
SOLID: SRP (data contracts only)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    """A single section in a generated report.

    Attributes:
        heading: Section heading displayed as H2.
        content: Body text in Markdown format.
        data: Optional list of row dicts to render as a table.
        chart_config: Optional ECharts config dict (stored in metadata; rendered
            by mcp-visualization in future pipeline integration).
    """

    heading: str
    content: str  # Markdown text
    data: list[dict[str, Any]] | None = None
    chart_config: dict[str, Any] | None = None


class GenerateReportRequest(BaseModel):
    """Input payload for the generate_report MCP tool.

    Attributes:
        title: Report title rendered at the top of every output format.
        sections: Ordered list of ReportSection objects.
        format: Output format — "pdf" or "pptx".
        tenant_id: Tenant identifier used for MinIO path isolation.
        include_provenance: Whether to embed the Merkle certificate.
    """

    title: str = Field(..., min_length=1, max_length=500)
    sections: list[ReportSection] = Field(..., min_length=1)
    format: Literal["pdf", "pptx"] = "pdf"
    tenant_id: str = Field(..., min_length=1)
    include_provenance: bool = True


class GenerateReportResponse(BaseModel):
    """Output payload for the generate_report MCP tool.

    Attributes:
        report_id: UUID4 assigned to this report.
        format: Actual output format produced.
        storage_path: MinIO object path where the report is stored.
        merkle_root: SHA-256 Merkle root of all section content claims.
        ipfs_hash: Pinata IPFS CID, present only when anchoring succeeded.
        page_count: Estimated page count (PDF) or actual slide count (PPTX).
        generation_ms: Wall-clock time in milliseconds for the full pipeline.
    """

    report_id: str
    format: str
    storage_path: str
    merkle_root: str
    ipfs_hash: str | None = None
    page_count: int
    generation_ms: float


class AnchorIPFSRequest(BaseModel):
    """Input payload for the anchor_ipfs MCP tool.

    Attributes:
        report_id: Existing report ID to anchor.
        merkle_root: SHA-256 Merkle root to anchor on IPFS.
        tenant_id: Tenant identifier (stored in Pinata metadata).
    """

    report_id: str
    merkle_root: str
    tenant_id: str


class AnchorIPFSResponse(BaseModel):
    """Successful IPFS anchoring result.

    Attributes:
        ipfs_hash: IPFS CID returned by Pinata.
        pinata_url: Public IPFS gateway URL.
        anchored_at: ISO-8601 UTC timestamp.
    """

    ipfs_hash: str
    pinata_url: str
    anchored_at: str
