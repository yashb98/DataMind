# Sequence Diagrams — Key User Journeys

> UML 2.5 Sequence Diagrams for the five most critical platform flows.
> Rendered with Mermaid.

---

## 1. Natural Language Query → Validated SQL → Dashboard Widget

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Next.js Frontend
    participant KG as Kong Gateway
    participant SR as SLM Router
    participant LG as LangGraph Orchestrator
    participant NA as NL-to-SQL Agent
    participant MS as mcp-sql-executor
    participant CH as ClickHouse
    participant AHP as Anti-Hallucination Pipeline
    participant MV as mcp-visualization
    participant LF as Langfuse

    U->>FE: "Show me revenue by region for Q3 2025"
    FE->>KG: POST /api/query {nl_query, tenant_id}
    KG->>SR: SLM Intent classify + Complexity score
    SR-->>KG: intent=NL_TO_SQL, complexity=medium
    KG->>LG: Route to NL-to-SQL Agent Team

    activate LG
    LG->>NA: Execute NL-to-SQL task

    activate NA
    NA->>MS: mcp.retrieve_schema(tenant_id)
    MS-->>NA: Schema + sample rows (MMR-retrieved)

    NA->>LF: Start trace span "nl_to_sql"
    NA->>LG: [LiteLLM] codestral:22b → generate SQL
    LG-->>NA: SELECT region, SUM(revenue) FROM sales WHERE quarter='Q3-2025' GROUP BY region

    NA->>MS: mcp.execute_sql(query)
    MS->>CH: Execute query
    CH-->>MS: ResultSet {rows: [...], latency: 45ms}
    MS-->>NA: Validated DataFrame

    NA->>AHP: Layer 8 — Numerical verification
    AHP->>MS: Re-verify aggregates via SQL COUNT check
    MS-->>AHP: Verified ✓
    AHP-->>NA: ValidationResult {passed: true, score: 0.98}

    NA->>MV: mcp.suggest_chart(data, intent)
    MV-->>NA: chart_type=bar, config={...}
    NA-->>LG: AgentResult {sql, data, chart_config, provenance_hash}
    deactivate NA

    LG->>LF: End trace, log tokens/latency/score
    LG-->>KG: Response {widget_config, data_url}
    deactivate LG

    KG-->>FE: 200 OK {widget_config}
    FE-->>U: Bar chart rendered (< 800ms total)
```

---

## 2. Data Ingestion → PII Masking → Lakehouse Storage

```mermaid
sequenceDiagram
    actor A as Admin / API Client
    participant DC as mcp-data-connector (Go)
    participant PR as Presidio PII Scanner
    participant FPE as FPE Masker
    participant EB as Schema Registry
    participant KF as Apache Kafka
    participant FL as Apache Flink
    participant IC as Apache Iceberg
    participant GE as Great Expectations
    participant OL as OpenLineage
    participant LF as Langfuse

    A->>DC: POST /ingest {source_type, credentials, dataset_id}
    DC->>DC: Connect to source (JDBC/REST/CDC)
    DC->>DC: Stream rows in batches (10k rows)

    DC->>PR: Scan batch for PII entities
    PR-->>DC: PII report {email: col3, name: col7, ip: col11}

    DC->>FPE: Mask PII columns (format-preserving)
    FPE-->>DC: Masked batch (col3=enc_email, col7=enc_name)

    DC->>PR: Tag metadata in PostgreSQL
    DC->>EB: Validate Avro schema compatibility
    EB-->>DC: Schema v3 compatible ✓

    DC->>KF: Produce events to topic "raw.ingestion.{tenant_id}"
    KF->>FL: Consume stream (exactly-once)

    activate FL
    FL->>FL: Stateful enrichment + sessionisation
    FL->>GE: Run DQ test suite on batch
    GE-->>FL: DQ result {null_rate: 0.001, schema_drift: false}
    FL->>IC: Write to Iceberg table (ACID, exactly-once)
    FL->>OL: Emit OpenLineage event
    OL->>OL: Update Marquez lineage graph
    deactivate FL

    IC-->>DC: Commit confirmed
    DC->>LF: Log ingestion trace {rows, pii_fields, latency}
    DC-->>A: 202 Accepted {job_id, estimated_completion}
```

---

## 3. Digital Worker Autonomous Weekly Report

```mermaid
sequenceDiagram
    participant CRON as Celery Beat Scheduler
    participant WM as Workforce Manager
    participant ECHO as Echo (Report Writer Worker)
    participant ARIA as Aria (Data Analyst Worker)
    participant LUNA as Luna (Risk Analyst Worker)
    participant MK as mcp-knowledge-base
    participant MS as mcp-sql-executor
    participant MR as mcp-report-generator
    participant CP as CryptographicProvenanceService
    participant SMTP as Email / Slack
    participant LF as Langfuse

    CRON->>WM: trigger("weekly_cfo_report", tenant_id)
    WM->>WM: Decompose goal into sub-tasks
    WM->>ARIA: Execute "Revenue performance EDA"
    WM->>LUNA: Execute "Risk metrics summary" (parallel)

    activate ARIA
    ARIA->>MS: run_nl_to_sql("weekly revenue by channel")
    MS-->>ARIA: DataFrame {revenue_data}
    ARIA->>ARIA: Run EDA, detect anomalies
    ARIA-->>WM: EDA Result + anomaly flags
    deactivate ARIA

    activate LUNA
    LUNA->>MK: retrieve("Q3 risk thresholds")
    MK-->>LUNA: Risk context chunks (MMR-retrieved)
    LUNA->>LUNA: Compute VaR, stress test
    LUNA-->>WM: Risk metrics report
    deactivate LUNA

    WM->>ECHO: Compile report from Aria+Luna outputs
    activate ECHO
    ECHO->>MR: generate_narrative(data, insights, risk)
    MR->>MR: LLM narrative generation (Claude claude-sonnet-4-6)
    MR->>CP: Hash all agent outputs → Merkle tree
    CP-->>MR: ProvenanceRecord {merkle_root, ipfs_cid}
    MR->>MR: Render PDF + PPTX + embed provenance cert
    MR-->>ECHO: Report artifacts
    ECHO-->>WM: Report complete

    WM->>LF: Log full workflow trace + scores
    WM->>SMTP: Send report to CFO + attach PDF
    SMTP-->>WM: Delivered ✓

    LF->>LF: LLM-as-judge eval: narrative quality score
    LF->>LF: Update Echo KPI metrics
```

---

## 4. Anti-Hallucination Validation Pipeline

```mermaid
sequenceDiagram
    participant AG as Agent (any)
    participant L1 as L1 Retrieval Grounding
    participant L2 as L2 NLI Faithfulness
    participant L3 as L3 Self-Consistency
    participant L4 as L4 CoT Audit (Critic)
    participant L5 as L5 Structured Output
    participant L6 as L6 KB Boundary
    participant L7 as L7 Temporal Grounding
    participant L8 as L8 Numerical Verify
    participant OUT as Validated Output

    AG->>L1: LLM Response + Source Chunks
    L1->>L1: Check all claims cite chunk IDs
    L1-->>L1: Flag uncited claims (amber)

    L1->>L2: Response + Context
    L2->>L2: DeBERTa-v3 NLI per factual claim
    alt Score < 0.7
        L2-->>AG: Regenerate request
    else Score ≥ 0.7
        L2->>L3: Pass to self-consistency check
    end

    L3->>L3: Is query high-stakes? (finance/medical/legal)
    alt High-stakes = YES
        L3->>L3: Sample 5 responses @ T=0.7
        L3->>L3: Majority vote on factual claims
        L3-->>L3: Confidence interval computed
    end

    L3->>L4: Reasoning chain
    L4->>L4: CriticAgent validates logical entailment
    alt Reasoning invalid
        L4-->>AG: Force CoT revision
    end

    L4->>L5: Output structure
    L5->>L5: Instructor + Pydantic schema validation
    alt Schema violation
        L5-->>AG: Re-generate with schema constraint
    end

    L5->>L6: Query scope check
    L6->>L6: SLM knowledge boundary classifier
    alt Query out of scope
        L6-->>AG: "Insufficient data" response
    end

    L6->>L7: Retrieved chunks
    L7->>L7: Check ingestion_date > 90 days
    L7-->>L7: Add staleness warnings to metadata

    L7->>L8: Numerical claims
    L8->>L8: SQL re-verify all numbers vs source
    alt Mismatch detected
        L8-->>AG: Correction request
    end

    L8->>OUT: Validated, scored, provenance-hashed output
```

---

## 5. SSO Authentication & ABAC Authorization Flow

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Next.js Frontend
    participant KG as Kong Gateway
    participant IDP as Okta/Auth0 (SAML 2.0 / OIDC)
    participant AUTH as Auth Service (FastAPI)
    participant VT as HashiCorp Vault
    participant ABAC as ABAC Policy Engine
    participant PG as PostgreSQL

    U->>FE: Navigate to app
    FE->>KG: GET /auth/login
    KG->>IDP: Redirect to SSO provider
    IDP->>U: Present login form + MFA
    U->>IDP: Credentials + TOTP
    IDP->>KG: SAML Assertion / ID Token (signed JWT)

    KG->>AUTH: POST /auth/verify {token}
    AUTH->>AUTH: Verify JWT signature + expiry
    AUTH->>PG: Lookup tenant_id, roles, permissions
    PG-->>AUTH: User profile {tenant_id, roles: [analyst]}
    AUTH->>VT: Get per-tenant encryption key
    VT-->>AUTH: AES-256 key (rotated 90 days)
    AUTH->>AUTH: Generate session token (HMAC-SHA256 pseudonym)
    AUTH-->>KG: Session established {session_id, permissions}

    KG->>ABAC: POST /authorize {user, action, resource}
    ABAC->>ABAC: Evaluate CEL rules
    Note over ABAC: Rule: analyst.can_read(table)\nWHERE table.sensitivity != RESTRICTED\nAND table.column NOT IN user.pii_excluded
    ABAC-->>KG: Allow/Deny + column-level mask list

    KG-->>FE: Authorized response + masked column list
    FE-->>U: Dashboard loads with permitted data only
```
