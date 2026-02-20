"""
Datasets router — Day 1 skeleton.
Full implementation: Day 4-6 (EPIC 1, mcp-data-connector).
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class DatasetConnectRequest(BaseModel):
    source_type: str  # postgresql | csv | s3 | snowflake | salesforce | ...
    credentials: dict
    tenant_id: str
    processing_purpose: str = "analytics"


@router.post("/connect")
async def connect_dataset(req: DatasetConnectRequest):
    """
    Connect an external data source and trigger ingestion.
    Handles PII scanning + masking before Kafka publishing.
    Full implementation: Day 4-6.
    """
    return {
        "status": "stub",
        "message": "Data connector not yet implemented (Day 4-6)",
        "source_type": req.source_type,
    }


@router.get("/{dataset_id}/profile")
async def get_dataset_profile(dataset_id: str, tenant_id: str):
    """Get statistical profile of a dataset."""
    return {"dataset_id": dataset_id, "status": "pending"}
