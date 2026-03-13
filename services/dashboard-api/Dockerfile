FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install uv --no-cache-dir
COPY pyproject.toml .
RUN uv venv .venv && uv pip install --python .venv/bin/python \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "asyncpg>=0.30.0" \
    "redis[hiredis]>=5.2.0" \
    "aiokafka>=0.11.0" \
    "httpx>=0.28.0" \
    "langfuse>=2.50.0" \
    "structlog>=24.4.0" \
    "opentelemetry-sdk>=1.28.0" \
    "opentelemetry-exporter-otlp>=1.28.0" \
    "opentelemetry-instrumentation-fastapi>=0.49b0" \
    "prometheus-client>=0.21.0" \
    "python-multipart>=0.0.12" \
    "websockets>=13.0"

FROM python:3.12-slim
RUN groupadd -r datamind && useradd -r -g datamind datamind
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY src/ /app/src/
RUN chown -R datamind:datamind /app
USER datamind
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1
EXPOSE 8110
HEALTHCHECK --interval=20s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8110/health/liveness').raise_for_status()"
CMD ["uvicorn", "dashboard_api.main:app", "--host", "0.0.0.0", "--port", "8110", "--workers", "2"]
