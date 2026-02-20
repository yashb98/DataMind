# ============================================================
# DataMind API — Multi-stage Dockerfile
# Stage 1: Dependencies
# Stage 2: Production image (minimal, no build tools)
# ============================================================

# Stage 1 — Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install uv==0.5.0 --no-cache-dir

# Copy dependency files first (Docker layer caching)
COPY pyproject.toml .

# Install dependencies into /build/.venv
RUN uv venv .venv && \
    uv pip install --python .venv/bin/python \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "langfuse>=2.55.0" \
    "litellm>=1.55.0" \
    "httpx>=0.28.0" \
    "structlog>=24.4.0" \
    "opentelemetry-sdk>=1.28.0" \
    "opentelemetry-exporter-otlp>=1.28.0" \
    "opentelemetry-instrumentation-fastapi>=0.49b0" \
    "asyncpg>=0.30.0" \
    "redis[hiredis]>=5.2.0" \
    "tenacity>=9.0.0"

# Stage 2 — Production runtime
FROM python:3.12-slim AS production

LABEL org.opencontainers.image.source="https://github.com/yashb98/DataMind"
LABEL org.opencontainers.image.description="DataMind API — AI-Native Analytics Platform"

# Non-root user for security
RUN groupadd -r datamind && useradd -r -g datamind datamind

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY src/ /app/src/

# Ensure non-root ownership
RUN chown -R datamind:datamind /app

USER datamind

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health/liveness').raise_for_status()"

CMD ["uvicorn", "datamind_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
