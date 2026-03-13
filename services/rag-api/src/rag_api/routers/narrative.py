"""
RAG API — Narrative Router.
Day 22: Phase 5 — generate/compile endpoints for NarrativeAgent + CompilerAgent.

Protocols: None (REST)
SOLID: SRP (routing only), DIP (agent instances from app.state)
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/narrative", tags=["Narrative"])

# ── In-memory report store (simple, per-process) ────────────────────────────
# In production this would be MinIO / Redis, but per the spec we keep it simple.
_REPORT_STORE: dict[str, bytes] = {}


# ── Request / Response models ────────────────────────────────────────────────


class SectionSpec(BaseModel):
    title: str = Field(..., min_length=1)
    type: str = Field(default="analysis")  # summary|analysis|recommendation|methodology
    data_context: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunkIn(BaseModel):
    chunk_id: str
    source_id: str
    content: str


class GenerateReportRequest(BaseModel):
    title: str = Field(..., min_length=1)
    sections_spec: list[SectionSpec] = Field(..., min_length=1)
    retrieved_chunks: list[RetrievedChunkIn] = Field(default_factory=list)
    tenant_id: str


class NarrativeSectionOut(BaseModel):
    section_id: str
    title: str
    body: str
    citations: list[str]
    confidence: float
    generation_ms: float
    section_type: str


class GenerateReportResponse(BaseModel):
    title: str
    tenant_id: str
    sections: list[NarrativeSectionOut]
    total_sections: int


class CompileReportRequest(BaseModel):
    report_id: str | None = None
    title: str = Field(..., min_length=1)
    sections: list[NarrativeSectionOut] = Field(..., min_length=1)
    tenant_id: str
    include_provenance: bool = True


class CompileReportResponse(BaseModel):
    report_id: str
    tenant_id: str
    title: str
    page_count: int
    merkle_root: str
    sections: list[str]
    generation_ms: float
    download_url: str


# ── Dependency helpers ────────────────────────────────────────────────────────


def _get_narrative_agent(request: Request) -> Any:
    agent = getattr(request.app.state, "narrative_agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="NarrativeAgent not initialised")
    return agent


def _get_compiler_agent(request: Request) -> Any:
    agent = getattr(request.app.state, "compiler_agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="CompilerAgent not initialised")
    return agent


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateReportResponse)
async def generate_report(
    body: GenerateReportRequest,
    narrative_agent: Any = Depends(_get_narrative_agent),
) -> GenerateReportResponse:
    """Generate all narrative sections for a report.

    Calls NarrativeAgent.generate_section() for each spec entry concurrently
    (via generate_report). Each section enforces [SOURCE chunk_id] citations.

    SLO: < 15s per section (LLM-dependent).
    """
    log.info(
        "narrative.generate_report.request",
        title=body.title,
        sections=len(body.sections_spec),
        tenant_id=body.tenant_id,
    )

    chunks_raw = [c.model_dump() for c in body.retrieved_chunks]

    try:
        sections = await narrative_agent.generate_report(
            sections_spec=[s.model_dump() for s in body.sections_spec],
            retrieved_chunks=chunks_raw,
            tenant_id=body.tenant_id,
        )
    except Exception as exc:
        log.error("narrative.generate_report.failed", error=str(exc), tenant_id=body.tenant_id)
        raise HTTPException(status_code=500, detail=f"Narrative generation failed: {exc}") from exc

    return GenerateReportResponse(
        title=body.title,
        tenant_id=body.tenant_id,
        sections=[
            NarrativeSectionOut(
                section_id=s.section_id,
                title=s.title,
                body=s.body,
                citations=s.citations,
                confidence=s.confidence,
                generation_ms=s.generation_ms,
                section_type=s.section_type,
            )
            for s in sections
        ],
        total_sections=len(sections),
    )


@router.post("/compile", response_model=CompileReportResponse)
async def compile_report(
    body: CompileReportRequest,
    compiler_agent: Any = Depends(_get_compiler_agent),
) -> CompileReportResponse:
    """Compile NarrativeSections into a PDF with Merkle provenance certificate.

    The generated PDF is stored in the in-process _REPORT_STORE keyed by
    report_id and is retrievable via GET /api/narrative/reports/{id}.

    SLO: < 30s for 10-page report.
    """
    from rag_api.narrative.narrative_agent import NarrativeSection  # noqa: PLC0415

    report_id = body.report_id or str(uuid.uuid4())

    # Reconstruct NarrativeSection dataclasses from the incoming Pydantic models
    sections = [
        NarrativeSection(
            section_id=s.section_id,
            title=s.title,
            body=s.body,
            citations=s.citations,
            confidence=s.confidence,
            generation_ms=s.generation_ms,
            section_type=s.section_type,
        )
        for s in body.sections
    ]

    log.info(
        "narrative.compile_report.request",
        report_id=report_id,
        title=body.title,
        sections=len(sections),
        tenant_id=body.tenant_id,
    )

    try:
        compiled = await compiler_agent.compile(
            report_id=report_id,
            title=body.title,
            sections=sections,
            tenant_id=body.tenant_id,
            include_provenance=body.include_provenance,
        )
    except Exception as exc:
        log.error("narrative.compile_report.failed", error=str(exc), report_id=report_id)
        raise HTTPException(status_code=500, detail=f"Report compilation failed: {exc}") from exc

    # Store PDF for later download
    _REPORT_STORE[compiled.report_id] = compiled.pdf_bytes

    return CompileReportResponse(
        report_id=compiled.report_id,
        tenant_id=compiled.tenant_id,
        title=compiled.title,
        page_count=compiled.page_count,
        merkle_root=compiled.merkle_root,
        sections=compiled.sections,
        generation_ms=compiled.generation_ms,
        download_url=f"/api/narrative/reports/{compiled.report_id}",
    )


@router.get("/reports/{report_id}")
async def download_report(report_id: str) -> Response:
    """Download a previously compiled PDF report.

    Args:
        report_id: The UUID of the compiled report.

    Returns:
        PDF file response (application/pdf).

    Raises:
        404: If the report_id is not found in the store.
    """
    pdf_bytes = _REPORT_STORE.get(report_id)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="datamind-report-{report_id}.pdf"',
            "X-Report-ID": report_id,
        },
    )
