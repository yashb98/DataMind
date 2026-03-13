"""
RAG API — DSR Router.
Day 22: Phase 5 — GDPR Art. 15, 17, 20 endpoints for Subject Access, Erasure, Portability.

Protocols: None (REST)
SOLID: SRP (routing only), DIP (DSRAutomation from app.state)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, EmailStr

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/dsr", tags=["DSR / GDPR"])


# ── Request / Response models ────────────────────────────────────────────────


class DSRRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    subject_email: str = Field(..., min_length=3)  # plain email string
    request_id: str | None = None


class DSRRecordCounts(BaseModel):
    store: str
    count: int


class SARResponse(BaseModel):
    request_id: str
    tenant_id: str
    subject_email: str
    request_type: str
    stores_processed: list[str]
    records_found: dict[str, int]
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    total_records: int


class ErasureResponse(BaseModel):
    request_id: str
    tenant_id: str
    subject_email: str
    request_type: str
    stores_processed: list[str]
    records_deleted: dict[str, int]
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    total_deleted: int
    certificate_url: str


class PortabilityResponse(BaseModel):
    request_id: str
    tenant_id: str
    subject_email: str
    request_type: str
    stores_processed: list[str]
    records_found: dict[str, int]
    total_records: int
    export_format: str
    data: dict[str, list[dict[str, Any]]]


# ── In-memory certificate store ──────────────────────────────────────────────
_CERTIFICATE_STORE: dict[str, bytes] = {}


# ── Dependency helpers ────────────────────────────────────────────────────────


def _get_dsr_automation(request: Request) -> Any:
    dsr = getattr(request.app.state, "dsr_automation", None)
    if dsr is None:
        raise HTTPException(status_code=503, detail="DSRAutomation not initialised")
    return dsr


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/sar", response_model=SARResponse)
async def subject_access_request(
    body: DSRRequest,
    dsr_automation: Any = Depends(_get_dsr_automation),
) -> SARResponse:
    """Execute a GDPR Art. 15 Subject Access Request.

    Searches all 6 data stores concurrently and returns a count of records
    found per store. The actual data export is performed via ``/portability``.

    SLO: < 30s (well within the 24h GDPR SLA).

    Args:
        body: DSR request with tenant_id, subject_email, optional request_id.

    Returns:
        SARResponse with records_found per store.
    """
    request_id = body.request_id or str(uuid.uuid4())
    log.info(
        "dsr.sar.request",
        request_id=request_id,
        tenant_id=body.tenant_id,
    )

    try:
        result = await dsr_automation.subject_access_request(
            tenant_id=body.tenant_id,
            subject_email=body.subject_email,
            request_id=request_id,
        )
    except Exception as exc:
        log.error("dsr.sar.failed", request_id=request_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"SAR failed: {exc}") from exc

    return SARResponse(
        request_id=result.request_id,
        tenant_id=result.tenant_id,
        subject_email=result.subject_email,
        request_type=result.request_type,
        stores_processed=result.stores_processed,
        records_found=result.records_found,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_ms=result.duration_ms,
        total_records=sum(result.records_found.values()),
    )


@router.post("/erasure", response_model=ErasureResponse)
async def erasure_request(
    body: DSRRequest,
    dsr_automation: Any = Depends(_get_dsr_automation),
) -> ErasureResponse:
    """Execute a GDPR Art. 17 Right to Erasure request.

    Deletes all records for the subject across all 6 data stores and
    generates a signed erasure completion certificate PDF.

    SLO: < 60s (well within the 72h GDPR SLA).

    Args:
        body: DSR request with tenant_id, subject_email, optional request_id.

    Returns:
        ErasureResponse with records_deleted per store and certificate_url.
    """
    request_id = body.request_id or str(uuid.uuid4())
    log.info(
        "dsr.erasure.request",
        request_id=request_id,
        tenant_id=body.tenant_id,
    )

    try:
        result = await dsr_automation.erasure_request(
            tenant_id=body.tenant_id,
            subject_email=body.subject_email,
            request_id=request_id,
        )
    except Exception as exc:
        log.error("dsr.erasure.failed", request_id=request_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Erasure failed: {exc}") from exc

    if result.certificate_pdf:
        _CERTIFICATE_STORE[result.request_id] = result.certificate_pdf

    return ErasureResponse(
        request_id=result.request_id,
        tenant_id=result.tenant_id,
        subject_email=result.subject_email,
        request_type=result.request_type,
        stores_processed=result.stores_processed,
        records_deleted=result.records_deleted,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_ms=result.duration_ms,
        total_deleted=sum(result.records_deleted.values()),
        certificate_url=f"/api/dsr/certificate/{result.request_id}",
    )


@router.post("/portability", response_model=PortabilityResponse)
async def portability_request(
    body: DSRRequest,
    dsr_automation: Any = Depends(_get_dsr_automation),
) -> PortabilityResponse:
    """Execute a GDPR Art. 20 Data Portability request.

    Performs a full SAR across all 6 stores and returns the raw records as
    structured JSON, formatted as a machine-readable export.

    SLO: < 60s.

    Args:
        body: DSR request with tenant_id, subject_email, optional request_id.

    Returns:
        PortabilityResponse with all found records per store as exportable JSON.
    """
    request_id = body.request_id or str(uuid.uuid4())
    log.info(
        "dsr.portability.request",
        request_id=request_id,
        tenant_id=body.tenant_id,
    )

    try:
        # Portability = SAR + format as data export
        result = await dsr_automation.subject_access_request(
            tenant_id=body.tenant_id,
            subject_email=body.subject_email,
            request_id=request_id,
        )
    except Exception as exc:
        log.error("dsr.portability.failed", request_id=request_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Portability export failed: {exc}") from exc

    # Build per-store data export structure
    # The SAR result contains counts; for portability we fetch the full records
    # by running search on each store directly
    export_data: dict[str, list[dict[str, Any]]] = {}
    for store in dsr_automation._stores:
        try:
            records = await store.search(
                tenant_id=body.tenant_id,
                subject_email=body.subject_email,
            )
            export_data[store.store_name] = [
                {k: str(v) if not isinstance(v, str | int | float | bool) else v
                 for k, v in r.items()}
                for r in records
            ]
        except Exception as exc:
            log.warning(
                "dsr.portability.store_failed",
                store=store.store_name,
                error=str(exc),
            )
            export_data[store.store_name] = []

    return PortabilityResponse(
        request_id=result.request_id,
        tenant_id=result.tenant_id,
        subject_email=result.subject_email,
        request_type="portability",
        stores_processed=result.stores_processed,
        records_found=result.records_found,
        total_records=sum(result.records_found.values()),
        export_format="JSON",
        data=export_data,
    )


@router.get("/certificate/{request_id}")
async def download_certificate(request_id: str) -> Response:
    """Download a GDPR erasure completion certificate PDF.

    Args:
        request_id: The DSR request ID whose certificate to download.

    Returns:
        PDF file response.

    Raises:
        404: If the certificate is not found.
    """
    cert_bytes = _CERTIFICATE_STORE.get(request_id)
    if cert_bytes is None:
        raise HTTPException(
            status_code=404,
            detail=f"Certificate for request {request_id} not found",
        )

    return Response(
        content=cert_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="erasure-certificate-{request_id}.pdf"'
            ),
            "X-Request-ID": request_id,
        },
    )
