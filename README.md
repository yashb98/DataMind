# DataMind

> **AI-Native Data Analytics & Data Science Platform** — Competing with Tableau and Power BI, powered by a 48-agent Digital Labor Workforce, multi-cloud lakehouse architecture, and verifiable AI.

---

## What is DataMind?

DataMind Enterprise is an open-architecture, multi-tenant SaaS platform that replaces traditional BI tools with an autonomous AI analytics layer. Instead of humans querying dashboards, **Digital Workers** — persistent AI agent personas — ingest your data, clean it, analyse it, build dashboards, detect anomalies, train models, and deliver boardroom-ready reports. Autonomously. Around the clock.

You describe the business goal. DataMind figures out the rest.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js 15 Frontend                      │
│         Dashboard Builder · NL Query · Workbench UI         │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│               Kong API Gateway + FastAPI                     │
│          LiteLLM Proxy · LangFuse Observability             │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│           Multi-Agent Orchestration Layer                    │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ LangGraph   │  │   CrewAI     │  │  AutoGen + ADK     │ │
│  │ Orchestrator│  │ Agent Teams  │  │  Meta + DS Agents  │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
│                                                             │
│  48 Agents across 3 tiers · Kafka messaging · gRPC tools   │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│              FastMCP Tool Server Layer                       │
│  python-sandbox · sql-executor · visualization · dbt-runner │
│  knowledge-base · report-generator · data-connector · more  │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│                   Data & AI Layer                            │
│                                                             │
│  PostgreSQL · ClickHouse · Qdrant · Neo4j · TimescaleDB     │
│  Apache Iceberg · Flink · Kafka · MinIO · Redis · MongoDB   │
│                                                             │
│  Claude claude-sonnet-4-6 · DeepSeek-R1 · Ollama (offline) │
│  vLLM · Axolotl QLoRA · WebLLM (edge) · Cloudflare Workers │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Capabilities

### 🤖 48-Agent Digital Labor Workforce
A three-tier agent architecture that autonomously executes complete analytics workflows — from raw data to executive report — with humans in a supervisory role, not an execution role.

- **Tier 1 — 12 Digital Workers:** Named, persistent AI personas (Aria the Analyst, Max the ETL Engineer, Luna the Risk Analyst, Quant the Quantum Optimiser...) with defined SLAs, KPIs, memory, and tool access
- **Tier 2 — 28 Specialist Agents:** Six domain teams (Intake, Data Engineering, Analytics, Data Science, Reporting, Meta) built on LangGraph, CrewAI, AutoGen, and Google ADK
- **Tier 3 — Always-On Services:** SLM intent classifier, NLI faithfulness scorer, edge inference, knowledge boundary detector

### 📊 Visualization & Dashboard Engine
- 25+ chart types (ECharts 5 + D3.js + deck.gl WebGL geospatial)
- Drag-and-drop dashboard builder with cross-filter interactions
- Natural language → full dashboard generation
- Real-time dashboards via WebSocket (< 1s refresh)
- Pixel-perfect PDF, PPTX, embeddable iframe export

### 🔬 Data Science Workbench
- Embedded JupyterHub with Python, R, SQL kernels
- AutoML via AutoGluon — 10+ algorithms, auto-selected and tuned
- Forecasting: Prophet, NeuralForecast (NHITS/TFT), Amazon Chronos
- Causal inference: DoWhy + EconML treatment effect estimation
- One-click model deployment → BentoML REST API
- Fine-tuning UI: upload data → configure LoRA → train → deploy

### 🧠 Hybrid RAG with MMR Retrieval
- **Maximal Marginal Relevance (MMR)** retrieval with adaptive lambda — diverse, non-redundant context for every query
- Hybrid search: Qdrant dense (cosine) + BM25 sparse → ColBERT re-ranking
- **GraphRAG** (Microsoft): entity-relationship graph over business documents in Neo4j
- 4-tier agent memory: short-term (Redis) · long-term (Qdrant) · episodic (MongoDB) · semantic (pgvector)
- RAGAS continuous evaluation: faithfulness, relevancy, context recall — nightly scoring

### 🛡️ 8-Layer Anti-Hallucination Stack
Every LLM output passes through:
1. Retrieval grounding with citation enforcement
2. NLI faithfulness scoring (DeBERTa-v3)
3. Self-consistency sampling (5-shot for high-stakes queries)
4. Chain-of-thought audit via CriticAgent
5. Structured output enforcement (Instructor + Pydantic)
6. Knowledge boundary detection (fine-tuned SLM)
7. Temporal grounding (chunk age flagging)
8. Numerical verification against source data via SQL

### ⚡ Three-Tier LLM Inference
| Tier | Models | Latency | Use Case |
|------|--------|---------|----------|
| Edge | Phi-3.5-mini (WebLLM/Workers AI) | < 20ms | Chart suggestions, intent routing |
| Local SLM | Phi-3.5-mini, Gemma-2-2B (Ollama) | < 50ms | Classification, complexity scoring |
| Local LLM | llama3.3:70b, deepseek-r1:32b, codestral:22b | < 500ms | Analysis, SQL generation, reasoning |
| Cloud | Claude claude-sonnet-4-6, GPT-4o, Gemini 1.5 Pro | < 1s | Complex reasoning, narrative, planning |
| RLM | DeepSeek-R1:32b, o3-mini | < 3s | Causal inference, hypothesis, deep reasoning |

Automatic failover to local Ollama when internet is unavailable. LiteLLM proxy unifies all providers.

### 🔭 Langfuse LLM Observability
- End-to-end tracing of every agent step, tool call, and LLM response
- Prompt versioning with A/B testing and hot-swap (no redeployment)
- LLM-as-judge automated evaluation pipeline (correctness, faithfulness, toxicity)
- Per-tenant, per-agent cost breakdown fed directly into Stripe billing
- Golden dataset curation from high-scoring traces → Axolotl fine-tuning

### 🔐 GDPR Privacy-by-Design
- Microsoft Presidio PII detection and format-preserving encryption (FPE) before every LLM call
- Automated Subject Access Request (SAR) portal — searches all stores, returns report in 24h
- Right to Erasure: removes data from PostgreSQL, Qdrant, MinIO, MongoDB, Neo4j within 72h SLA
- Data residency enforcement at Kubernetes topology level (EU data stays in eu-west-1)
- Post-quantum cryptography: CRYSTALS-Kyber (KEM) + CRYSTALS-Dilithium (signatures)
- Automated DPIA generation for new data source onboarding

### ☁️ Amorphous Hybrid Multi-Cloud
- **Conductor Policy Engine** (CEL rules): workloads fluidly placed across AWS, GCP, Azure, and on-prem based on cost, latency, data residency, and GPU availability
- Apache Iceberg lakehouse with Project Nessie (git-like data branching)
- Apache Flink 1.19 stateful stream processing → real-time Iceberg sinks
- DuckDB embedded for sub-second medium-dataset analytics (no external engine)
- Apache Arrow Flight for 10-100x faster internal DataFrame transfer vs REST
- Hourly spot price arbitrage across clouds for ML training jobs

### ⚛️ Quantum Utility
- **D-Wave QUBO**: feature selection as quadratic optimisation — faster than classical exhaustive search on 50+ features
- **PennyLane**: quantum neural networks as AutoGluon custom model type
- **AWS Braket**: IonQ/Rigetti/OQC hardware access for circuit experiments
- **Quantum RNG**: cryptographically superior seeds for Monte Carlo simulations
- Quantum-safe cryptography throughout (NIST PQC standards)

### ✅ Verifiable AI
- SHA-256 hash of every AI output (query + context + model + prompt version + result)
- Merkle tree evidence chain for multi-agent reports — every claim traceable to source
- IPFS-anchored report hashes via Pinata for tamper-evident external verification
- Confidence intervals on all model predictions (no point estimates without uncertainty)
- Auto-generated model cards and dataset datasheets for every artifact

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | Next.js 15, React 19, Tailwind v4, shadcn/ui, ECharts 5, D3.js, deck.gl, AG Grid, Monaco, Zustand |
| **Backend** | FastAPI (Python 3.12), Go 1.22, Bun, Kong, gRPC, Pydantic v2 |
| **Agent Frameworks** | LangGraph, CrewAI, AutoGen, Google ADK, FastMCP |
| **LLM / AI** | Claude claude-sonnet-4-6, GPT-4o, Gemini 1.5 Pro, LiteLLM, Ollama, vLLM, Axolotl QLoRA |
| **RAG** | Qdrant, LlamaIndex, ColBERT, GraphRAG, RAGAS, BAAI/bge-m3, BM25s |
| **Databases** | PostgreSQL 16+pgvector, ClickHouse, TimescaleDB, Redis 7, MongoDB, Neo4j, Qdrant, MinIO |
| **Data Engineering** | Apache Iceberg, Flink, Kafka, Spark, dbt, DuckDB, Arrow Flight, Nessie, OpenLineage |
| **MLOps** | MLflow, Feast, AutoGluon, ZenML, BentoML, Triton, Evidently AI, Optuna, SHAP |
| **Observability** | Langfuse, OpenTelemetry, Grafana, Prometheus, Loki, Jaeger |
| **Cloud** | AWS (EKS, MSK, Braket, Bedrock), GCP (Vertex AI, BigQuery), Azure (Synapse, OpenAI), Cloudflare |
| **Infra** | Kubernetes, Helm, Terraform, ArgoCD, Istio, KEDA, HashiCorp Vault |
| **Quantum** | D-Wave Leap, PennyLane, AWS Braket, CRYSTALS-Kyber/Dilithium |
| **Security** | Presidio, LLM Guard, SAML 2.0, OIDC, ABAC, Snyk, Trivy |

---

## Agent Teams

```
DataMind Orchestrator (LangGraph)
├── Intake Team          → DataConnector · SchemaInference · DataProfiling
├── Data Engineering     → Cleaning · Transformation · Quality · Enrichment
├── Analytics            → EDA · Statistics · NL-to-SQL · Insight · Visualization
├── Data Science         → Hypothesis · Features · ModelSelection · Training · Eval · Causal · Forecast
├── Reporting            → Narrative · Compiler · Presentation
├── Meta                 → Planner · Critic · MemoryConsolidation · MetaEvaluator
└── Digital Workers (12) → Aria · Max · Luna · Atlas · Nova · Sage · Echo · Iris · Rex · Geo · Swift · Quant
```

**Total: 48 agents across 3 tiers**

---

## Build Plan

DataMind is built across a structured **28-day engineering sprint** across 6 phases:

| Phase | Days | Focus |
|-------|------|-------|
| 1 | 1–7 | Foundation: monorepo, auth, LiteLLM, Kafka, observability |
| 2 | 8–14 | Agent backbone: FastMCP, LangGraph, RAG, NL-to-SQL |
| 3 | 15–17 | Visualization: 25 chart types, AI dashboard builder |
| 4 | 18–21 | Data science: JupyterHub, AutoML, forecasting, model deploy |
| 5 | 22–23 | RAG & reporting: agent memory, GraphRAG, narrative engine |
| 6 | 24–28 | Enterprise: SSO, billing, white-label, Kubernetes, launch |

---

## Performance Targets

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| Edge chart suggestion | < 20ms | < 50ms | < 100ms |
| SLM intent classification | < 30ms | < 80ms | < 150ms |
| Dashboard load (cached) | < 50ms | < 150ms | < 300ms |
| NL-to-SQL + execution | < 800ms | < 1.5s | < 3s |
| LLM first token (streaming) | < 100ms | < 300ms | < 600ms |
| Full RAG query | < 600ms | < 1.2s | < 2s |
| Agent workflow (simple) | < 3s | < 8s | < 15s |
| Digital Worker task | < 1min | < 3min | < 5min |

---

## Status

> 🚧 **Active Development** — Following the 28-day build plan. Architecture and planning documents complete. Implementation in progress.

---

## License

Proprietary — All rights reserved. Contact for enterprise licensing and white-label enquiries.

---

<p align="center">Built with 🧠 by a Digital Labor Workforce, for the humans who want their data to think for itself.</p>
