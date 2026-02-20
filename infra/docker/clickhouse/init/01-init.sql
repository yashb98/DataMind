-- DataMind ClickHouse Init — Day 2
-- Analytics tables, materialised views skeleton, Langfuse backend

-- ============================================================
-- Databases
-- ============================================================
CREATE DATABASE IF NOT EXISTS analytics;
CREATE DATABASE IF NOT EXISTS langfuse;

-- ============================================================
-- Analytics Database: Core Tables
-- ============================================================

-- Raw events: every user action, query, agent execution
CREATE TABLE IF NOT EXISTS analytics.events (
    event_id        UUID DEFAULT generateUUIDv4(),
    tenant_id       UUID NOT NULL,
    user_id         UUID,
    event_type      LowCardinality(String) NOT NULL, -- query/dashboard_view/agent_task/login/...
    source          LowCardinality(String) NOT NULL, -- web/api/worker/scheduler
    properties      String CODEC(ZSTD(3)),           -- JSON blob
    session_id      UUID,
    created_at      DateTime64(3, 'UTC') NOT NULL DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, event_type, created_at)
TTL created_at + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- Agent task metrics: latency, cost, tokens per task type
CREATE TABLE IF NOT EXISTS analytics.agent_tasks (
    task_id         UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    worker_id       UUID,
    task_type       LowCardinality(String) NOT NULL,
    agent_name      LowCardinality(String) NOT NULL,
    llm_model       LowCardinality(String) NOT NULL,
    status          LowCardinality(String) NOT NULL,
    input_tokens    UInt32 DEFAULT 0,
    output_tokens   UInt32 DEFAULT 0,
    total_cost_usd  Float64 DEFAULT 0,
    latency_ms      UInt32 DEFAULT 0,
    confidence      Float32 DEFAULT 0,
    eval_score      Float32 DEFAULT 0,
    created_at      DateTime64(3, 'UTC') NOT NULL DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, agent_name, created_at)
TTL created_at + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Dashboard query cache hit/miss tracking
CREATE TABLE IF NOT EXISTS analytics.dashboard_queries (
    query_id        UUID DEFAULT generateUUIDv4(),
    tenant_id       UUID NOT NULL,
    dashboard_id    UUID,
    widget_id       UUID,
    query_fingerprint String NOT NULL,   -- SHA-256 of normalised SQL
    cache_hit       Bool NOT NULL DEFAULT false,
    latency_ms      UInt32 NOT NULL DEFAULT 0,
    result_rows     UInt32 DEFAULT 0,
    created_at      DateTime64(3, 'UTC') NOT NULL DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, created_at)
TTL created_at + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- LLM cost tracking: unified across all providers via LiteLLM
CREATE TABLE IF NOT EXISTS analytics.llm_costs (
    trace_id        UUID NOT NULL,
    tenant_id       UUID NOT NULL,
    agent_name      LowCardinality(String) NOT NULL,
    model           LowCardinality(String) NOT NULL,
    provider        LowCardinality(String) NOT NULL,
    input_tokens    UInt32 NOT NULL DEFAULT 0,
    output_tokens   UInt32 NOT NULL DEFAULT 0,
    cost_usd        Float64 NOT NULL DEFAULT 0,
    latency_ms      UInt32 DEFAULT 0,
    created_at      DateTime64(3, 'UTC') NOT NULL DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, provider, model, created_at)
TTL created_at + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- Ingestion pipeline metrics
CREATE TABLE IF NOT EXISTS analytics.ingestion_runs (
    run_id          UUID NOT NULL DEFAULT generateUUIDv4(),
    tenant_id       UUID NOT NULL,
    dataset_id      UUID NOT NULL,
    source_type     LowCardinality(String) NOT NULL,
    rows_ingested   UInt64 DEFAULT 0,
    rows_rejected   UInt64 DEFAULT 0,
    pii_fields_masked UInt32 DEFAULT 0,
    dq_pass         Bool NOT NULL DEFAULT true,
    duration_ms     UInt32 DEFAULT 0,
    created_at      DateTime64(3, 'UTC') NOT NULL DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (tenant_id, dataset_id, created_at)
SETTINGS index_granularity = 8192;

-- ============================================================
-- Materialised Views: Pre-aggregated for sub-10ms dashboard queries
-- ============================================================

-- Daily LLM cost by tenant + model
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_daily_llm_cost
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (tenant_id, day, provider, model)
AS SELECT
    tenant_id,
    toDate(created_at) AS day,
    provider,
    model,
    sum(input_tokens)  AS total_input_tokens,
    sum(output_tokens) AS total_output_tokens,
    sum(cost_usd)      AS total_cost_usd,
    count()            AS request_count
FROM analytics.llm_costs
GROUP BY tenant_id, day, provider, model;

-- Hourly agent task performance
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_hourly_agent_perf
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (tenant_id, hour, agent_name, task_type)
AS SELECT
    tenant_id,
    toStartOfHour(created_at) AS hour,
    agent_name,
    task_type,
    countState()                           AS task_count,
    avgState(latency_ms)                   AS avg_latency,
    quantileState(0.99)(latency_ms)        AS p99_latency,
    avgState(eval_score)                   AS avg_eval_score,
    sumState(total_cost_usd)               AS total_cost,
    countIfState(status = 'completed')     AS success_count,
    countIfState(status = 'failed')        AS failure_count
FROM analytics.agent_tasks
GROUP BY tenant_id, hour, agent_name, task_type;

-- Daily active users per tenant
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_daily_active_users
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (tenant_id, day)
AS SELECT
    tenant_id,
    toDate(created_at) AS day,
    uniqExact(user_id) AS dau,
    count()            AS total_events
FROM analytics.events
WHERE user_id IS NOT NULL
GROUP BY tenant_id, day;

-- Cache hit rate for dashboard queries
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_cache_hit_rate
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (tenant_id, hour)
AS SELECT
    tenant_id,
    toStartOfHour(created_at) AS hour,
    countIf(cache_hit = true)  AS cache_hits,
    countIf(cache_hit = false) AS cache_misses,
    count()                    AS total_queries,
    avg(latency_ms)            AS avg_latency_ms
FROM analytics.dashboard_queries
GROUP BY tenant_id, hour;
