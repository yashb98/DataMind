# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir hatchling pip --upgrade

# Copy project definition first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/

# Build wheel
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# Install all deps into a prefix
RUN pip install --no-cache-dir --prefix=/install /wheels/*.whl


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: non-root user
RUN groupadd --gid 1001 datamind && \
    useradd --uid 1001 --gid datamind --shell /bin/bash --create-home datamind

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy source
COPY --chown=datamind:datamind src/ ./src/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER datamind

EXPOSE 8130

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8130/health/liveness')" || exit 1

CMD ["uvicorn", "rag_api.main:app", "--host", "0.0.0.0", "--port", "8130"]
