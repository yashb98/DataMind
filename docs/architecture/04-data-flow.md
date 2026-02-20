# Data Flow Diagrams & Entity Relationship Diagrams

---

## 1. End-to-End Data Flow — DFD Level 0

```mermaid
flowchart LR
    EXT([External Data Sources\nDB / S3 / API / CDC]) -->|Raw Streams| ING[Ingestion\nmcp-data-connector]
    ING -->|PII-masked\nAvro events| KF[(Kafka Topics)]
    KF -->|Stream| FL[Flink Processing\nCEP + Sessionisation]
    KF -->|Batch replay| SP[Spark ETL\nHistorical]
    FL -->|ACID writes| IC[(Iceberg Lakehouse\nMinIO)]
    SP --> IC
    IC -->|DuckDB read| AG[Agent MCP Tools]
    IC -->|ClickHouse import| CH[(ClickHouse OLAP)]
    CH -->|SQL| AG
    AG -->|Results| LLM[LLM Inference\nLiteLLM / vLLM]
    LLM -->|Validated output| UI[Dashboard / Reports]
```

---

## 2. Agent Memory Architecture — Data Flow

```mermaid
flowchart TB
    subgraph MEMORY["🧠  4-Tier Agent Memory"]
        STM[Short-Term Memory\nRedis — Session Context\nTTL 30 min]
        LTM[Long-Term Memory\nQdrant — Semantic Search\nPersistent per Worker]
        EPI[Episodic Memory\nMongoDB — Past Task Logs\nRetention 1yr]
        SEM[Semantic Memory\nPostgreSQL pgvector\nFacts + Relationships]
    end

    A[Agent Receives Task] --> STM
    STM -->|Working context| PROC[Agent Processing]
    PROC -->|Vector similarity search| LTM
    PROC -->|Past decisions lookup| EPI
    PROC -->|Factual grounding| SEM
    PROC -->|New learnings| CONS[Memory Consolidation Agent]
    CONS -->|Summarise + compress| LTM
    CONS -->|Log episode| EPI
    CONS -->|Extract facts| SEM
```

---

## 3. Core Entity Relationship Diagram

```mermaid
erDiagram
    TENANT {
        uuid tenant_id PK
        string name
        string plan_tier
        string data_region
        timestamp created_at
        bool gdpr_enabled
    }

    USER {
        uuid user_id PK
        uuid tenant_id FK
        string email_hash
        string role
        jsonb permissions
        timestamp last_login
    }

    DIGITAL_WORKER {
        uuid worker_id PK
        uuid tenant_id FK
        string name
        string role
        jsonb capabilities
        string llm_model
        float cost_per_task
        float performance_score
        string status
    }

    TASK {
        uuid task_id PK
        uuid worker_id FK
        uuid tenant_id FK
        string task_type
        jsonb input_params
        jsonb output_artifact
        float confidence_score
        int latency_ms
        timestamp created_at
        timestamp completed_at
    }

    LANGFUSE_TRACE {
        uuid trace_id PK
        uuid task_id FK
        uuid tenant_id FK
        string agent_name
        string model_used
        int input_tokens
        int output_tokens
        float cost_usd
        int latency_ms
        float eval_score
        string prompt_version
    }

    DATASET {
        uuid dataset_id PK
        uuid tenant_id FK
        string source_type
        string iceberg_table_path
        jsonb schema
        jsonb pii_columns
        string processing_purpose
        timestamp ingested_at
        string retention_policy
    }

    PROVENANCE_RECORD {
        uuid record_id PK
        uuid task_id FK
        string merkle_root_hash
        string ipfs_cid
        jsonb agent_output_hashes
        timestamp created_at
        bool verified
    }

    DSR_REQUEST {
        uuid dsr_id PK
        uuid tenant_id FK
        string subject_email_hash
        string request_type
        string status
        timestamp requested_at
        timestamp completed_at
        string completion_certificate
    }

    WORKER_MEMORY {
        uuid memory_id PK
        uuid worker_id FK
        string memory_type
        vector embedding
        text content
        float importance_score
        timestamp created_at
        timestamp expires_at
    }

    TENANT ||--o{ USER : "has"
    TENANT ||--o{ DIGITAL_WORKER : "employs"
    TENANT ||--o{ DATASET : "owns"
    TENANT ||--o{ DSR_REQUEST : "receives"
    DIGITAL_WORKER ||--o{ TASK : "executes"
    DIGITAL_WORKER ||--o{ WORKER_MEMORY : "stores"
    TASK ||--o| LANGFUSE_TRACE : "generates"
    TASK ||--o| PROVENANCE_RECORD : "creates"
    DATASET }|--o{ TASK : "consumed by"
```

---

## 4. Lakehouse Storage Topology

```mermaid
graph TB
    subgraph BRONZE["🟤  Bronze Layer — Raw"]
        B1[raw.ingestion.{tenant}]
        B2[Avro/JSON — exact as received]
        B3[PII masked before storage]
    end

    subgraph SILVER["⚪  Silver Layer — Cleaned"]
        S1[cleaned.{domain}.{entity}]
        S2[Parquet on Iceberg]
        S3[DQ tested, deduplicated]
        S4[Schema normalised]
    end

    subgraph GOLD["🟡  Gold Layer — Aggregated"]
        G1[mart.{domain}.{metric}]
        G2[Pre-aggregated dimensions]
        G3[Dashboard-ready]
        G4[ClickHouse import]
    end

    subgraph PLATINUM["💎  Platinum Layer — AI-Ready"]
        P1[features.{model}.{version}]
        P2[Training datasets]
        P3[Feature Store (Feast)]
        P4[Embedding snapshots]
    end

    BRONZE -->|Flink CEP + DQ| SILVER
    SILVER -->|dbt models| GOLD
    GOLD -->|Feature engineering| PLATINUM
    GOLD --> CH[(ClickHouse OLAP)]
    PLATINUM --> FS[(Feast Feature Store)]
    FS --> ML[ML Training\nAutoGluon / Axolotl]
```

---

## 5. Multi-Cloud Data Residency Flow

```mermaid
flowchart TB
    REQ[Incoming Data Request] --> CD{Conductor Policy Engine\nCEL Rules}

    CD -->|data_region=EU| AWS_EU[AWS eu-west-1\nIreland]
    CD -->|data_region=US| AWS_US[AWS us-east-1\nVirginia]
    CD -->|data_region=APAC| GCP_AP[GCP asia-east1\nTaiwan]
    CD -->|model_size > 70B| ONPREM[On-Prem GPU Cluster]
    CD -->|burst > 100 concurrent| GCP_SPOT[GCP Spot Instances\nCost Arbitrage]

    AWS_EU --> EU_ICEBERG[(Iceberg — eu-west-1\nAES-256 per-tenant key\nVault rotation 90d)]
    AWS_US --> US_ICEBERG[(Iceberg — us-east-1)]
    GCP_AP --> AP_ICEBERG[(Iceberg — asia-east1)]

    EU_ICEBERG -->|Never leaves EU| EU_CH[(ClickHouse — eu-west-1)]
    EU_CH --> EU_DASH[EU Dashboards]

    subgraph KEYS["🔐  Key Management"]
        VT[HashiCorp Vault]
        VT --> EU_KEY[EU Tenant Key\n90-day rotation]
        VT --> US_KEY[US Tenant Key]
        EU_KEY --> EU_ICEBERG
    end
```
