# Process Mapping — BPMN-Style Platform Workflows

> Maps every major operational process in DataMind using swimlane diagrams.
> Rendered with Mermaid flowcharts (BPMN notation).

---

## 1. New Tenant Onboarding Process

```mermaid
flowchart TD
    START([New Customer Signs Up]) --> PLAN{Select Plan\nStarter/Pro/Enterprise}

    PLAN -->|Starter/Pro| SAAS[SaaS Flow]
    PLAN -->|Enterprise| ENT[Enterprise Flow]

    SAAS --> STRIPE[Stripe Checkout\nCredit Card]
    STRIPE --> TENANT_CREATE[Create Tenant Record\nPostgreSQL]

    ENT --> SALES[Sales Engineering\nCall + DPA Signing]
    SALES --> DPA[Auto-generate DPA\nper Sub-processors]
    DPA --> VPC[Provision Dedicated\nVPC / Namespace]
    VPC --> TENANT_CREATE

    TENANT_CREATE --> VAULT[Provision Encryption Keys\nHashiCorp Vault]
    VAULT --> DB_SCHEMA[Create Tenant Schema\nPostgreSQL + ClickHouse]
    DB_SCHEMA --> WORKER_DEPLOY[Deploy 12 Digital Workers\nWorker Registry]
    WORKER_DEPLOY --> SSO{SSO Required?}

    SSO -->|Yes| SAML[Configure SAML 2.0\nor OIDC connector]
    SSO -->|No| EMAIL_AUTH[Email + Password\n+ MFA setup]
    SAML --> GDPR_CONF
    EMAIL_AUTH --> GDPR_CONF

    GDPR_CONF[GDPR Configuration\nData region\nRetention policy\nConsent settings]
    GDPR_CONF --> CONN[Connect First Data Source\nmcp-data-connector wizard]
    CONN --> INGEST[Trigger First Ingestion\n+ DQ validation]
    INGEST --> ONBOARD_DONE([Tenant Active ✓\nDashboard ready])
```

---

## 2. AI Query Processing Workflow (Happy Path + Error Paths)

```mermaid
flowchart TD
    START([User Submits NL Query]) --> RATE{Rate Limit\nCheck Kong}
    RATE -->|Exceeded| 429[429 Too Many Requests\n+ Retry-After header]
    RATE -->|OK| AUTHZ{ABAC Authorization\nCheck}
    AUTHZ -->|Denied| 403[403 Forbidden\n+ reason]
    AUTHZ -->|Allowed| SLM[SLM Router\nIntent + Complexity]

    SLM --> TIER{Inference Tier\nSelection}
    TIER -->|Edge < 20ms| CF_EDGE[Cloudflare Workers AI\nEdge Response]
    TIER -->|SLM < 100ms| LOCAL[Ollama Local\nSLM Response]
    TIER -->|Standard| CLOUD[LiteLLM → Cloud LLM]
    TIER -->|Complex| RLM[vLLM DeepSeek-R1\nRLM Reasoning]

    CLOUD --> LLM_CALL[LLM Generates Response]
    RLM --> LLM_CALL

    LLM_CALL --> AHP[Anti-Hallucination Pipeline\n8 Layers]
    AHP --> AHP_PASS{Validation\nPassed?}
    AHP_PASS -->|Layer 2 fail\nFaithfulness < 0.7| REGEN[Regenerate\nmax 3 attempts]
    REGEN --> LLM_CALL
    AHP_PASS -->|Layer 6 fail\nOut of scope| INSUFF[Return: Insufficient Data\nPlain explanation]
    AHP_PASS -->|All layers pass| PROV[Cryptographic Provenance\nSHA-256 + Merkle]

    PROV --> TRACE[Langfuse Trace\nTokens + Cost + Score]
    TRACE --> RESP[Stream Response\nSSE to Frontend]
    CF_EDGE --> RESP
    LOCAL --> RESP
    RESP --> DONE([User Sees Result])
```

---

## 3. Data Subject Rights (DSR) — Right to Erasure (Art. 17)

```mermaid
flowchart TD
    START([Subject Submits Erasure Request\nvia SAR Portal]) --> VERIFY{Identity\nVerification}
    VERIFY -->|Failed| DENY[Request Denied\n+ instructions]
    VERIFY -->|OK| TICKET[Create DSR Ticket\nJira/Linear\n72h SLA timer starts]

    TICKET --> SEARCH[Search ALL Stores\nfor subject_email_hash]

    SEARCH --> PG_DEL[Delete from PostgreSQL\nUser data + audit rows]
    SEARCH --> CH_DEL[Delete from ClickHouse\nAnalytics events]
    SEARCH --> QD_DEL[Tombstone Qdrant\nVector embeddings]
    SEARCH --> MN_DEL[Delete MinIO objects\nUploaded files]
    SEARCH --> MG_DEL[Delete MongoDB\nEpisodic memory logs]
    SEARCH --> N4_DEL[Delete Neo4j nodes\nKnowledge graph]

    PG_DEL --> VERIFY_DEL{All Deletions\nConfirmed?}
    CH_DEL --> VERIFY_DEL
    QD_DEL --> VERIFY_DEL
    MN_DEL --> VERIFY_DEL
    MG_DEL --> VERIFY_DEL
    N4_DEL --> VERIFY_DEL

    VERIFY_DEL -->|Any Failed| RETRY[Retry Failed\nDeletion Jobs]
    RETRY --> VERIFY_DEL
    VERIFY_DEL -->|All Done| CERT[Generate Completion\nCertificate PDF]

    CERT --> NOTIFY[Email Certificate\nto Subject + DPO]
    NOTIFY --> CLOSE[Close DSR Ticket\nAudit Log Entry]
    CLOSE --> DONE([Erasure Complete\nWithin 72h SLA ✓])

    subgraph SLA["72h SLA Monitoring"]
        TIMER[Celery Beat\nSLA countdown]
        ALERT[DPO Alert if\n> 48h elapsed]
        ESC[Legal Team Escalation\nif > 60h]
    end
```

---

## 4. Digital Worker Autonomous Workflow Execution

```mermaid
flowchart TD
    TRIGGER([Trigger: Cron / Event / Manual]) --> WM[Workforce Manager\nGoal Received]
    WM --> DECOMP[Goal Decomposition\nLLM-powered planning]
    DECOMP --> TASKS[Task List Generated\nWith Dependencies]
    TASKS --> ASSIGN{Assign to\nOptimal Workers}

    ASSIGN --> W1[Worker A\nRunning]
    ASSIGN --> W2[Worker B\nRunning in Parallel]
    ASSIGN --> W3[Worker C\nWaiting on A]

    W1 --> W1_EXEC{Task\nCompleted?}
    W1_EXEC -->|Success| W1_OUT[Artifact Output\n+ Handoff Message]
    W1_EXEC -->|Confidence < 0.7| HUMAN_GATE{Human Approval\nGate}
    W1_EXEC -->|Error| W1_ERR[Escalate to Human\nWith context + options]

    HUMAN_GATE -->|Approved| W1_OUT
    HUMAN_GATE -->|Rejected| W1_REVISE[Worker Revises\nWith feedback]
    W1_REVISE --> W1_EXEC

    W1_OUT --> W3
    W2 --> W2_OUT[Artifact Output]
    W2_OUT --> W3

    W3 --> W3_EXEC{Final Task\nDone?}
    W3_EXEC -->|Success| REPORT[Compile Final Output\nEcho Report Writer]
    REPORT --> PROV[Add Provenance\nMerkle + IPFS]
    PROV --> LF_LOG[Log to Langfuse\nWorker KPIs Updated]
    LF_LOG --> DELIVER[Deliver via\nSlack / Email / Dashboard]
    DELIVER --> DONE([Workflow Complete\nSLA Tracked ✓])

    W1_ERR --> KILL{Admin:\nKill Switch?}
    KILL -->|Yes| GRACEFUL[Graceful Stop\nAll Workers\nNo data corruption]
    KILL -->|No| RESUME[Wait for Human\nInstruction]
```

---

## 5. CI/CD Pipeline — Code to Production

```mermaid
flowchart LR
    DEV([Developer Push\nto Feature Branch]) --> GH[GitHub PR Created]
    GH --> LINT[Lint + Type Check\npylint + mypy + eslint]
    LINT --> UNIT[Unit Tests\npytest + jest]
    UNIT --> SOLID_CHECK[SOLID Compliance\nimport-linter]
    SOLID_CHECK --> SEC[Security Scan\nSnyk + Trivy + Bandit]
    SEC --> BUILD[Docker Build\nMulti-stage, minimal]
    BUILD --> PUSH[Push to Registry\nECR / GCR / ACR]
    PUSH --> HELM_LINT[Helm Chart Lint\n+ Template Render]
    HELM_LINT --> INT_TEST[Integration Tests\nTestcontainers]
    INT_TEST --> REVIEW{Code Review\n2 approvers required}
    REVIEW -->|Changes Requested| REVISE[Developer Revises]
    REVISE --> GH
    REVIEW -->|Approved| MERGE[Merge to main]
    MERGE --> ARGOCD[ArgoCD Sync\nKubernetes Manifest]
    ARGOCD --> STAGING[Deploy to Staging\nSmoke Tests]
    STAGING --> LOAD[Load Test\nk6 — p99 < 2s]
    LOAD --> CANARY[Canary Deploy\n10% production traffic]
    CANARY --> METRICS{SLO Metrics\nOK for 30min?}
    METRICS -->|Error rate spike| ROLLBACK[Automatic Rollback\nArgoCD]
    METRICS -->|All green| FULL[Full Production Deploy\n100% traffic]
    FULL --> NOTIFY_DONE([Slack: Deploy ✓\nVersion + Changelog])
```

---

## 6. Model Fine-Tuning & Deployment Pipeline (MLOps)

```mermaid
flowchart TD
    TRIGGER([Trigger: Langfuse Score Drift\nor Manual Request]) --> DATA_CUR[Dataset Curation\nLangfuse golden pairs\nscore > 0.9]
    DATA_CUR --> SDV{Contains PII?}
    SDV -->|Yes| SYNTH[Generate Synthetic\nSDV / Gretel.ai]
    SDV -->|No| SPLIT[Train/Val/Test Split\n80/10/10]
    SYNTH --> SPLIT

    SPLIT --> MLFLOW[MLflow Experiment\nStart Run]
    MLFLOW --> AXOLOTL[Axolotl LoRA Fine-Tuning\nQLoRA 4-bit on A100]
    AXOLOTL --> EVAL[Eval on Test Set\nRAGAS + task-specific metrics]
    EVAL --> COMPARE{Better than\nBaseline?}
    COMPARE -->|No improvement| DISCARD[Discard Run\nLog reason to MLflow]
    COMPARE -->|Improved| MODEL_CARD[Auto-generate Model Card\nGoogle format]

    MODEL_CARD --> PQC[Sign with CRYSTALS-Dilithium\nTamper detection]
    PQC --> REGISTER[Register to MLflow\nModel Registry]
    REGISTER --> SHADOW[Shadow Deploy\n1% traffic alongside current]
    SHADOW --> A_B{A/B Langfuse\nEval 7 days}
    A_B -->|New model wins| PROMOTE[Promote to Production\nvLLM hot-reload]
    A_B -->|No improvement| ROLLBACK_M[Keep Current Model\nLog experiment]
    PROMOTE --> FEAST[Update Feast\nFeature Store version]
    FEAST --> NOTIFY_ML([Notify Team\nModel v{n} Deployed ✓])
```
