-- DataMind PostgreSQL Initialisation Script
-- Day 1: Create extensions, schemas, and core tables

-- ============================================================
-- Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;

-- ============================================================
-- Schemas (bounded domain separation — SRP at DB level)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS tenants;     -- Multi-tenancy
CREATE SCHEMA IF NOT EXISTS agents;      -- Agent state & memory
CREATE SCHEMA IF NOT EXISTS workflows;   -- Digital worker tasks
CREATE SCHEMA IF NOT EXISTS gdpr;        -- GDPR / DSR / PII tracking
CREATE SCHEMA IF NOT EXISTS observability; -- Langfuse / audit
CREATE SCHEMA IF NOT EXISTS features;    -- Feature store metadata

-- Langfuse needs its own database
CREATE DATABASE langfuse OWNER datamind;

-- ============================================================
-- TENANTS schema
-- ============================================================
CREATE TABLE tenants.tenants (
    tenant_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          TEXT NOT NULL,
    plan_tier     TEXT NOT NULL DEFAULT 'starter'
                  CHECK (plan_tier IN ('starter', 'pro', 'enterprise')),
    data_region   TEXT NOT NULL DEFAULT 'us-east-1',
    gdpr_enabled  BOOLEAN NOT NULL DEFAULT false,
    stripe_customer_id TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tenants.users (
    user_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    email_hash    TEXT NOT NULL,  -- HMAC-SHA256 pseudonym — never store plaintext
    role          TEXT NOT NULL DEFAULT 'analyst'
                  CHECK (role IN ('admin', 'analyst', 'data_scientist', 'viewer', 'dpo')),
    permissions   JSONB NOT NULL DEFAULT '{}',
    last_login    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_tenant ON tenants.users(tenant_id);

-- ============================================================
-- AGENTS schema
-- ============================================================
CREATE TABLE agents.digital_workers (
    worker_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id          UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    role               TEXT NOT NULL,
    capabilities       TEXT[] NOT NULL DEFAULT '{}',
    assigned_tools     TEXT[] NOT NULL DEFAULT '{}',
    llm_model          TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    sla_response_time_s INTEGER NOT NULL DEFAULT 30,
    cost_per_task_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0,
    performance_score  NUMERIC(4, 3) NOT NULL DEFAULT 1.0
                       CHECK (performance_score BETWEEN 0 AND 1),
    status             TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'paused', 'training', 'retired')),
    template_name      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workers_tenant ON agents.digital_workers(tenant_id);
CREATE INDEX idx_workers_status ON agents.digital_workers(status);

CREATE TABLE agents.worker_memory (
    memory_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_id       UUID NOT NULL REFERENCES agents.digital_workers(worker_id) ON DELETE CASCADE,
    memory_type     TEXT NOT NULL CHECK (memory_type IN ('semantic', 'episodic', 'procedural')),
    content         TEXT NOT NULL,
    embedding       vector(1024),        -- BAAI/bge-m3 dimension
    importance_score NUMERIC(4, 3) DEFAULT 0.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ          -- NULL = permanent
);

CREATE INDEX idx_memory_worker ON agents.worker_memory(worker_id);
CREATE INDEX idx_memory_embedding ON agents.worker_memory USING ivfflat (embedding vector_cosine_ops);

-- ============================================================
-- WORKFLOWS schema
-- ============================================================
CREATE TABLE workflows.tasks (
    task_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_id         UUID REFERENCES agents.digital_workers(worker_id),
    tenant_id         UUID NOT NULL REFERENCES tenants.tenants(tenant_id),
    task_type         TEXT NOT NULL,
    input_params      JSONB NOT NULL DEFAULT '{}',
    output_artifact   JSONB,
    confidence_score  NUMERIC(4, 3),
    latency_ms        INTEGER,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'running', 'completed', 'failed', 'paused')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_tasks_tenant ON workflows.tasks(tenant_id);
CREATE INDEX idx_tasks_worker ON workflows.tasks(worker_id);
CREATE INDEX idx_tasks_status ON workflows.tasks(status);

-- TimescaleDB hypertable for task metrics time-series
SELECT create_hypertable('workflows.tasks', 'created_at', if_not_exists => TRUE);

CREATE TABLE workflows.provenance_records (
    record_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id           UUID NOT NULL REFERENCES workflows.tasks(task_id),
    merkle_root_hash  TEXT NOT NULL,
    ipfs_cid          TEXT,
    agent_output_hashes JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified          BOOLEAN NOT NULL DEFAULT false
);

-- ============================================================
-- GDPR schema
-- ============================================================
CREATE TABLE gdpr.datasets (
    dataset_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants.tenants(tenant_id),
    source_type         TEXT NOT NULL,
    iceberg_table_path  TEXT,
    schema_snapshot     JSONB NOT NULL DEFAULT '{}',
    pii_columns         JSONB NOT NULL DEFAULT '{}',
    processing_purpose  TEXT NOT NULL DEFAULT 'analytics'
                        CHECK (processing_purpose IN ('analytics', 'training', 'reporting', 'testing')),
    legal_basis         TEXT NOT NULL DEFAULT 'legitimate_interest',
    data_region         TEXT NOT NULL,
    retention_policy    TEXT NOT NULL DEFAULT '2_years',
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE gdpr.dsr_requests (
    dsr_id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id              UUID NOT NULL REFERENCES tenants.tenants(tenant_id),
    subject_email_hash     TEXT NOT NULL,
    request_type           TEXT NOT NULL
                           CHECK (request_type IN ('access', 'erasure', 'portability', 'rectification')),
    status                 TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
    jira_ticket_id         TEXT,
    requested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at           TIMESTAMPTZ,
    completion_certificate TEXT     -- PDF URL
);

CREATE INDEX idx_dsr_tenant ON gdpr.dsr_requests(tenant_id);
CREATE INDEX idx_dsr_status ON gdpr.dsr_requests(status);

CREATE TABLE gdpr.legal_basis_registry (
    registry_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id      UUID NOT NULL REFERENCES tenants.tenants(tenant_id),
    processing_activity TEXT NOT NULL,
    legal_basis    TEXT NOT NULL,
    data_categories TEXT[] NOT NULL DEFAULT '{}',
    retention_period TEXT NOT NULL,
    sub_processors TEXT[] NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- OBSERVABILITY schema
-- ============================================================
CREATE TABLE observability.audit_log (
    log_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id      UUID NOT NULL,
    user_id        UUID,
    action         TEXT NOT NULL,
    resource_type  TEXT NOT NULL,
    resource_id    TEXT,
    metadata       JSONB NOT NULL DEFAULT '{}',
    ip_address     TEXT,  -- pseudonymised
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log is append-only — use TimescaleDB for efficient time queries
SELECT create_hypertable('observability.audit_log', 'created_at', if_not_exists => TRUE);

-- ============================================================
-- Seed: Default worker templates
-- ============================================================
INSERT INTO tenants.tenants (tenant_id, name, plan_tier, gdpr_enabled)
VALUES ('00000000-0000-0000-0000-000000000001', 'DataMind Demo Tenant', 'enterprise', true)
ON CONFLICT DO NOTHING;
