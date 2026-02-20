"""
DataMind Embedding Service — Day 2
BAAI/bge-m3 multilingual embeddings (1024-dim) with Qdrant collection management.

Responsibilities:
  - Embed text documents / queries via bge-m3
  - Manage Qdrant collections (create, configure, health)
  - Expose batch embed endpoint for MCP knowledge-base tool

SOLID:
  SRP — only embedding and collection management, no RAG logic
  DIP — QdrantClient injected, not instantiated inline
"""
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
import torch
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    HnswConfigDiff,
    OptimizersConfigDiff,
    QuantizationConfig,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from embedding_service.config import settings

log = structlog.get_logger(__name__)

# ---- Metrics ---------------------------------------------------------------
EMBED_COUNTER  = Counter("embedding_requests_total", "Total embedding requests", ["collection"])
EMBED_LATENCY  = Histogram("embedding_latency_ms", "Embedding latency in ms",
                            buckets=[10, 25, 50, 100, 250, 500, 1000])
UPSERT_COUNTER = Counter("qdrant_upserts_total", "Total Qdrant point upserts", ["collection"])

# ---- Qdrant collection definitions ----------------------------------------
# Each collection is ISOLATED by purpose (SRP at data level)
COLLECTIONS = {
    "knowledge_base": {
        "description": "RAG chunks from customer documents",
        "vector_size": 1024,
    },
    "agent_memory": {
        "description": "Long-term semantic memory for Digital Workers",
        "vector_size": 1024,
    },
    "entity_graph": {
        "description": "GraphRAG entity embeddings (linked to Neo4j)",
        "vector_size": 1024,
    },
    "schema_metadata": {
        "description": "Database schema + column embeddings for NL-to-SQL",
        "vector_size": 1024,
    },
}

# ---- Global state ----------------------------------------------------------
_model: SentenceTransformer | None = None
_qdrant: QdrantClient | None = None


def _build_vector_params() -> VectorParams:
    return VectorParams(
        size=1024,
        distance=Distance.COSINE,
        on_disk=False,                       # hot — keep in RAM
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=200,
            full_scan_threshold=10_000,
        ),
    )


def _build_quantization() -> QuantizationConfig:
    return QuantizationConfig(
        scalar=ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                quantile=0.99,
                always_ram=True,
            )
        )
    )


async def _ensure_collections(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    for name, meta in COLLECTIONS.items():
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=_build_vector_params(),
                quantization_config=_build_quantization(),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20_000,
                    memmap_threshold=100_000,
                ),
            )
            log.info("qdrant.collection_created", name=name, description=meta["description"])
        else:
            log.debug("qdrant.collection_exists", name=name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _qdrant

    # OTel
    provider = TracerProvider(
        resource=Resource.create({"service.name": "datamind-embedding"})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    # Load bge-m3 model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("embedding.model_loading", model=settings.embedding_model, device=device)
    _model = SentenceTransformer(settings.embedding_model, device=device)
    log.info("embedding.model_ready", model=settings.embedding_model)

    # Connect Qdrant + ensure collections
    _qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    await _ensure_collections(_qdrant)

    log.info("embedding.startup_complete")
    yield

    log.info("embedding.shutdown")


app = FastAPI(
    title="DataMind Embedding Service",
    description="BAAI/bge-m3 embeddings + Qdrant collection management",
    version="0.1.0",
    lifespan=lifespan,
)

FastAPIInstrumentor.instrument_app(app)
app.mount("/metrics", make_asgi_app())


# ---- Request / Response Models ---------------------------------------------
class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=512)
    normalize: bool = True


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimensions: int
    count: int


class UpsertRequest(BaseModel):
    collection: str
    ids: list[str]
    texts: list[str]
    payloads: list[dict] | None = None


class UpsertResponse(BaseModel):
    collection: str
    upserted: int
    status: str


# ---- Endpoints -------------------------------------------------------------
@app.get("/health/liveness")
async def liveness():
    return {"status": "alive", "service": "embedding"}


@app.get("/health/readiness")
async def readiness():
    model_ok = _model is not None
    qdrant_ok = False
    if _qdrant:
        try:
            _qdrant.get_collections()
            qdrant_ok = True
        except Exception:
            pass
    status = "healthy" if (model_ok and qdrant_ok) else "degraded"
    return {"status": status, "model": model_ok, "qdrant": qdrant_ok}


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    """Embed a list of texts using BAAI/bge-m3. Returns 1024-dim vectors."""
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    import time
    start = time.perf_counter()

    embeddings = _model.encode(
        req.texts,
        normalize_embeddings=req.normalize,
        batch_size=32,
        show_progress_bar=False,
    ).tolist()

    latency_ms = (time.perf_counter() - start) * 1000
    EMBED_LATENCY.observe(latency_ms)
    EMBED_COUNTER.labels(collection="direct").inc(len(req.texts))

    return EmbedResponse(
        embeddings=embeddings,
        model=settings.embedding_model,
        dimensions=len(embeddings[0]) if embeddings else 0,
        count=len(embeddings),
    )


@app.post("/upsert", response_model=UpsertResponse)
async def upsert(req: UpsertRequest):
    """Embed texts and upsert as Qdrant points into the named collection."""
    if _model is None or _qdrant is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    if req.collection not in COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{req.collection}'. Valid: {list(COLLECTIONS)}",
        )
    if len(req.ids) != len(req.texts):
        raise HTTPException(status_code=400, detail="ids and texts must have equal length")

    embeddings = _model.encode(
        req.texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    ).tolist()

    from qdrant_client.http.models import PointStruct
    points = [
        PointStruct(
            id=req.ids[i],
            vector=embeddings[i],
            payload=(req.payloads[i] if req.payloads else {}),
        )
        for i in range(len(req.ids))
    ]

    _qdrant.upsert(collection_name=req.collection, points=points, wait=True)
    UPSERT_COUNTER.labels(collection=req.collection).inc(len(points))

    log.info("embedding.upserted", collection=req.collection, count=len(points))
    return UpsertResponse(collection=req.collection, upserted=len(points), status="success")


@app.get("/collections")
async def list_collections():
    """List all Qdrant collections with point counts."""
    if _qdrant is None:
        raise HTTPException(status_code=503, detail="Qdrant not connected")
    cols = _qdrant.get_collections().collections
    result = []
    for col in cols:
        info = _qdrant.get_collection(col.name)
        result.append({
            "name": col.name,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": info.status,
        })
    return {"collections": result}
