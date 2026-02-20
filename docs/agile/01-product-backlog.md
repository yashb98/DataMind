# DataMind — Product Backlog

> **Total Epics:** 8 | **Total Stories:** ~120 | **Total Sprints:** 14 (28 days)
> Priority: 🔴 Must Have | 🟡 Should Have | 🟢 Could Have | ⚪ Won't Have (this release)

---

## EPIC 1 — Foundation & Infrastructure (Days 1–7)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E1-S1 | Turborepo monorepo with apps/web, apps/api, services/* structure | 3 | 🔴 | 1 | Builds clean |
| E1-S2 | Docker Compose with all 12 core services | 5 | 🔴 | 1 | All services healthy |
| E1-S3 | Kong API Gateway with JWT auth plugin | 5 | 🔴 | 1 | Auth works E2E |
| E1-S4 | LiteLLM Proxy with Claude, GPT-4o, Gemini, Ollama routing | 5 | 🔴 | 1 | All 4 providers route |
| E1-S5 | Langfuse self-hosted Docker service + PostgreSQL backend | 5 | 🔴 | 1 | Traces visible in UI |
| E1-S6 | Apache Kafka 5-broker cluster + Schema Registry | 5 | 🔴 | 1 | Topics created, produce/consume |
| E1-S7 | PostgreSQL 16 + pgvector + TimescaleDB extensions | 3 | 🔴 | 1 | Extensions enabled |
| E1-S8 | ClickHouse cluster + materialised view skeleton | 5 | 🔴 | 2 | Query returns in < 10ms |
| E1-S9 | Qdrant vector store + BAAI/bge-m3 embedding service | 5 | 🔴 | 2 | Vector search works |
| E1-S10 | Redis Sentinel 3-node cluster | 3 | 🔴 | 2 | Failover tested |
| E1-S11 | MinIO object storage + Iceberg REST catalog (Nessie) | 5 | 🔴 | 2 | Iceberg table created |
| E1-S12 | OpenTelemetry Collector + Grafana + Prometheus + Loki | 5 | 🔴 | 2 | Metrics visible |
| E1-S13 | Ollama SLM (Phi-3.5-mini + Gemma-2-2B) deployment | 3 | 🔴 | 2 | Models respond < 100ms |
| E1-S14 | SLM Router — intent classifier + complexity scorer | 5 | 🔴 | 3 | Routes correctly on test set |

---

## EPIC 2 — Agent Backbone (Days 8–14)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E2-S1 | mcp-python-sandbox FastMCP server (Go) | 8 | 🔴 | 3 | Executes Python safely |
| E2-S2 | mcp-sql-executor FastMCP server (Go) | 8 | 🔴 | 3 | SQL runs + returns DataFrame |
| E2-S3 | mcp-visualization FastMCP server (Node.js/ECharts) | 5 | 🔴 | 4 | Renders 5 basic chart types |
| E2-S4 | mcp-knowledge-base with MMR Qdrant retrieval | 8 | 🔴 | 4 | MMR improves diversity score |
| E2-S5 | LangGraph Orchestrator skeleton with StateGraph | 5 | 🔴 | 3 | State flows through graph |
| E2-S6 | Intake Agent Team (DataConnector + SchemaInference + DataProfiling) | 8 | 🔴 | 4 | Profiles CSV correctly |
| E2-S7 | NL-to-SQL Agent with schema RAG + SQL verification | 8 | 🔴 | 4 | 90%+ accuracy on test set |
| E2-S8 | DataCleaningAgent with Presidio PII masking | 5 | 🔴 | 4 | PII masked before LLM |
| E2-S9 | Anti-Hallucination Pipeline L1-L8 | 13 | 🔴 | 5 | All 8 layers tested |
| E2-S10 | EDAAgent with statistical analysis + InsightAgent | 8 | 🔴 | 5 | Insights generated accurately |
| E2-S11 | DeBERTa-v3 NLI faithfulness scorer (L2) | 5 | 🔴 | 5 | Faithfulness score computed |
| E2-S12 | Cryptographic provenance — SHA-256 + Merkle + IPFS | 5 | 🟡 | 5 | Hash stored + IPFS CID returned |
| E2-S13 | RLM escalation in LangGraph (DeepSeek-R1:32b) | 8 | 🟡 | 6 | Complex queries routed to RLM |
| E2-S14 | Langfuse @observe decorators on all agent nodes | 3 | 🔴 | 5 | Traces visible with spans |

---

## EPIC 3 — Visualisation & Dashboard (Days 15–17)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E3-S1 | Next.js 15 app scaffolding (App Router + Tailwind v4) | 5 | 🔴 | 6 | Dev server starts |
| E3-S2 | 25 chart types via ECharts 5 + D3.js | 8 | 🔴 | 7 | All charts render correctly |
| E3-S3 | Drag-and-drop dashboard builder | 8 | 🔴 | 7 | Widgets snap to grid |
| E3-S4 | WebSocket real-time dashboard updates (< 1s refresh) | 5 | 🔴 | 7 | WS push triggers re-render |
| E3-S5 | deck.gl WebGL geospatial choropleth + scatter | 5 | 🟡 | 7 | Map renders with data |
| E3-S6 | AI chart recommendation (Cloudflare Workers AI) | 5 | 🟡 | 8 | Suggests correct chart type |
| E3-S7 | WebLLM browser-local annotation suggestions | 3 | 🟢 | 8 | Phi-3.5-mini loads in browser |
| E3-S8 | Redis query result cache + ClickHouse materialised views | 5 | 🔴 | 8 | p99 dashboard load < 300ms |
| E3-S9 | PDF + PPTX export with provenance certificate | 5 | 🟡 | 8 | PDF includes Merkle cert |

---

## EPIC 4 — Data Science Workbench (Days 18–21)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E4-S1 | JupyterHub embedded (Python + R + SQL kernels) | 8 | 🔴 | 9 | Notebooks run in namespace |
| E4-S2 | AutoGluon AutoML integration (10 algorithms) | 8 | 🔴 | 9 | Trains on sample dataset |
| E4-S3 | Prophet + NeuralForecast + Chronos forecasting | 8 | 🔴 | 9 | Forecast with confidence intervals |
| E4-S4 | DoWhy + EconML causal inference | 5 | 🟡 | 10 | Causal graph generated |
| E4-S5 | HypothesisAgent + CausalInferenceAgent (RLM) | 8 | 🟡 | 10 | DeepSeek-R1 chain-of-thought |
| E4-S6 | MLflow experiment tracking + model registry | 5 | 🔴 | 9 | Runs tracked, models registered |
| E4-S7 | BentoML REST API deployment for trained models | 5 | 🟡 | 10 | Model serves predictions |
| E4-S8 | D-Wave QUBO feature selection (quantum utility) | 5 | 🟢 | 11 | QUBO problem solved on cloud |
| E4-S9 | CRYSTALS-Kyber/Dilithium on MLflow artifacts | 3 | 🟡 | 11 | Signed artifacts verified |
| E4-S10 | Self-consistency sampling for forecasts | 5 | 🟡 | 10 | 5-sample confidence band |

---

## EPIC 5 — RAG & Reporting (Days 22–23)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E5-S1 | 4-tier agent memory (Redis + Qdrant + MongoDB + pgvector) | 8 | 🔴 | 11 | Memory persists across sessions |
| E5-S2 | GraphRAG — Microsoft entity graphs in Neo4j | 8 | 🟡 | 11 | Graph queries return results |
| E5-S3 | RAGAS continuous evaluation pipeline | 5 | 🟡 | 11 | RAGAS scores tracked in MLflow |
| E5-S4 | mcp-report-generator (NarrativeAgent + WeasyPrint PDF) | 8 | 🔴 | 12 | 10-page report in < 60s |
| E5-S5 | LLM-as-judge eval pipeline in Langfuse (nightly) | 5 | 🟡 | 12 | Scores stored, alerts on drop |
| E5-S6 | DSR automation — SAR portal + erasure workflow | 8 | 🔴 | 12 | Art. 17 completed in < 72h |

---

## EPIC 6 — Enterprise Security & Compliance (Days 24–25)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E6-S1 | SAML 2.0 / OIDC SSO (Okta/Auth0) | 8 | 🔴 | 12 | SSO login flow works |
| E6-S2 | ABAC column-level access control | 8 | 🔴 | 12 | Restricted columns hidden |
| E6-S3 | Flink access anomaly detection + breach notification | 5 | 🟡 | 13 | Alert fires on spike |
| E6-S4 | Conductor multi-cloud policy engine (EU data residency) | 8 | 🟡 | 13 | EU data stays in eu-west-1 |
| E6-S5 | Automated DPIA generation for new datasets | 3 | 🟡 | 13 | DPIA PDF generated |
| E6-S6 | Celery Beat retention automation | 3 | 🔴 | 13 | Old data auto-deleted |

---

## EPIC 7 — Digital Labor Workforce (Day 26)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E7-S1 | Worker Registry (PostgreSQL schema + CRUD API) | 5 | 🔴 | 13 | Workers registered |
| E7-S2 | Workforce Manager LangGraph orchestrator | 8 | 🔴 | 13 | Goal decomposition works |
| E7-S3 | 12 pre-built Digital Worker templates | 8 | 🔴 | 13 | All workers deployable |
| E7-S4 | Workforce Dashboard UI (Next.js) | 5 | 🔴 | 13 | Real-time KPI display |
| E7-S5 | Kill Switch API + Graceful shutdown | 3 | 🔴 | 13 | All workers paused safely |
| E7-S6 | Worker KPI tracking via Langfuse evals | 5 | 🟡 | 14 | KPIs update in dashboard |

---

## EPIC 8 — Latency & Production Hardening (Days 27–28)

| ID | Story | Points | Priority | Sprint | DoD Check |
|----|-------|--------|----------|--------|-----------|
| E8-S1 | vLLM speculative decoding (Llama-3.2-1B draft) | 5 | 🔴 | 14 | 2x throughput verified |
| E8-S2 | Flash Attention 2 + INT8 KV cache quantisation | 3 | 🔴 | 14 | GPU memory 2x reduced |
| E8-S3 | KEDA event-driven autoscaling (Kafka lag trigger) | 5 | 🔴 | 14 | Pods scale on lag |
| E8-S4 | Prometheus SLO alerts (p99 > target fires) | 3 | 🔴 | 14 | Alert triggers on test |
| E8-S5 | Load test with k6 — p99 < 2s verified | 5 | 🔴 | 14 | Load test report green |
| E8-S6 | E2E GDPR compliance checklist verification | 5 | 🔴 | 14 | All 14 checklist items green |
| E8-S7 | Langfuse eval benchmarks (golden dataset) | 5 | 🟡 | 14 | Scores above baseline |
| E8-S8 | Quantum utility smoke tests (D-Wave + PennyLane) | 3 | 🟢 | 14 | QUBO runs without error |
