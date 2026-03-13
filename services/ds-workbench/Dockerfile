# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv==0.5.14

# Copy project definition
COPY pyproject.toml .
COPY src/ src/

# Create venv and install all dependencies
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache . && \
    uv pip install --no-cache "uvicorn[standard]>=0.32.0"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r datamind && useradd -r -g datamind -s /sbin/nologin datamind

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY --chown=datamind:datamind src/ src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER datamind

EXPOSE 8120

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8120/health/liveness').raise_for_status()"

CMD ["uvicorn", "ds_workbench.main:app", "--host", "0.0.0.0", "--port", "8120", "--workers", "2"]
