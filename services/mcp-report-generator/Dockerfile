FROM python:3.12-slim AS builder

WORKDIR /build

# System deps required by WeasyPrint (Pango, Cairo, GDK-Pixbuf, libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv --no-cache-dir

COPY pyproject.toml .

RUN uv venv .venv && uv pip install --python .venv/bin/python \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "mcp[cli]>=1.0.0" \
    "weasyprint>=62.0" \
    "python-pptx>=1.0.0" \
    "minio>=7.2.0" \
    "httpx>=0.28.0" \
    "langfuse>=2.50.0" \
    "structlog>=24.4.0" \
    "opentelemetry-sdk>=1.28.0" \
    "opentelemetry-exporter-otlp>=1.28.0" \
    "opentelemetry-instrumentation-fastapi>=0.49b0" \
    "prometheus-client>=0.21.0" \
    "markdown>=3.7" \
    "jinja2>=3.1.0"

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Same WeasyPrint system deps needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi8 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r datamind && useradd -r -g datamind datamind

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY src/ /app/src/

RUN chown -R datamind:datamind /app

USER datamind

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health/liveness').raise_for_status()"

CMD ["uvicorn", "mcp_report_generator.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
