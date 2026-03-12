FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install uv --no-cache-dir
COPY pyproject.toml .
RUN uv venv .venv && uv pip install --python .venv/bin/python \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "langgraph>=0.2.0" \
    "langchain-core>=0.3.0" \
    "langchain-community>=0.3.0" \
    "litellm>=1.55.0" \
    "langfuse>=2.50.0" \
    "instructor>=1.6.0" \
    "redis[hiredis]>=5.2.0" \
    "asyncpg>=0.30.0" \
    "httpx>=0.28.0" \
    "structlog>=24.4.0" \
    "opentelemetry-sdk>=1.28.0" \
    "opentelemetry-exporter-otlp>=1.28.0" \
    "opentelemetry-instrumentation-fastapi>=0.49b0" \
    "prometheus-client>=0.21.0" \
    "tenacity>=9.0.0" \
    "python-multipart>=0.0.12"

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
EXPOSE 8060
HEALTHCHECK --interval=20s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8060/health/liveness').raise_for_status()"
CMD ["uvicorn", "orchestration_engine.main:app", "--host", "0.0.0.0", "--port", "8060", "--workers", "2"]
