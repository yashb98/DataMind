# System Overview — C4 Context & Container Diagrams

> **UML Standard:** C4 Model (Context → Container → Component → Code)
> **Rendered with:** Mermaid (GitHub-native)

---

## Level 1 — System Context Diagram

Shows DataMind in relation to external actors and systems.

```mermaid
C4Context
    title DataMind — System Context

    Person(analyst, "Business Analyst", "Queries data in natural language, views dashboards")
    Person(ds, "Data Scientist", "Trains models, runs experiments in Workbench")
    Person(admin, "Platform Admin", "Manages tenants, workers, compliance, billing")
    Person(cfo, "CFO / Executive", "Reads AI-generated reports, monitors KPIs")

    System(datamind, "DataMind", "AI-native data analytics & digital labor platform. 48 agents, RAG, AutoML, Dashboards, GDPR-compliant.")

    System_Ext(llm_cloud, "Cloud LLMs", "Anthropic Claude, OpenAI GPT-4o, Google Gemini, AWS Bedrock")
    System_Ext(data_sources, "Customer Data Sources", "PostgreSQL, Snowflake, S3, Salesforce, Shopify, Google Sheets, REST APIs")
    System_Ext(dwave, "D-Wave Leap", "Quantum annealing cloud API for QUBO optimisation")
    System_Ext(cloudflare, "Cloudflare", "CDN, Workers AI edge inference, R2 storage, D1 SQLite")
    System_Ext(stripe, "Stripe", "Usage-based billing, subscription management")
    System_Ext(idp, "Identity Provider", "Okta / Auth0 — SAML 2.0, OIDC, MFA")
    System_Ext(ipfs, "IPFS / Pinata", "Immutable report hash anchoring for Verifiable AI")
    System_Ext(slack, "Slack / Email", "Alert delivery, report distribution, DSR notifications")

    Rel(analyst, datamind, "Natural language queries, dashboard exploration", "HTTPS")
    Rel(ds, datamind, "Python notebooks, AutoML, model deployment", "HTTPS / WS")
    Rel(admin, datamind, "Tenant management, worker config, compliance portal", "HTTPS")
    Rel(cfo, datamind, "Report consumption, KPI monitoring", "HTTPS / Email")

    Rel(datamind, llm_cloud, "LLM inference via LiteLLM proxy", "HTTPS/REST")
    Rel(datamind, data_sources, "Data ingestion via connectors", "JDBC/REST/CDC")
    Rel(datamind, dwave, "QUBO feature selection jobs", "HTTPS REST")
    Rel(datamind, cloudflare, "Edge inference, CDN, model weights", "HTTPS")
    Rel(datamind, stripe, "Token usage metering, invoicing", "HTTPS REST")
    Rel(datamind, idp, "SSO authentication flows", "SAML/OIDC")
    Rel(datamind, ipfs, "Report hash publishing", "IPFS API")
    Rel(datamind, slack, "Alerts, reports, notifications", "Webhook/SMTP")
```

---

## Level 2 — Container Diagram

Shows all major deployable units inside DataMind.

```mermaid
C4Container
    title DataMind — Container Diagram

    Person(user, "User", "Analyst / Data Scientist / Admin")

    Container_Boundary(frontend, "Frontend Layer") {
        Container(web, "Next.js 15 App", "React 19, Tailwind v4", "Dashboard builder, NL query UI, Workbench, Admin portal")
        Container(weblm, "WebLLM", "WASM/WebGPU", "Browser-local Phi-3.5-mini — chart suggestions, PII pre-screen")
    }

    Container_Boundary(gateway_layer, "API Gateway Layer") {
        Container(kong, "Kong API Gateway", "Kong 3.x", "Rate limiting, auth, routing, plugin pipeline")
        Container(litellm, "LiteLLM Proxy", "Python", "Unified LLM routing across 6 providers, cost tracking, Langfuse callback")
    }

    Container_Boundary(agent_layer, "Multi-Agent Orchestration") {
        Container(langgraph, "LangGraph Orchestrator", "Python / LangGraph", "Workforce Manager: goal decomposition, worker assignment, parallel execution")
        Container(crewai, "CrewAI Agent Teams", "Python / CrewAI", "Intake, Cleaning, Analytics, Reporting specialist teams")
        Container(autogen, "AutoGen CriticAgent", "Python / AutoGen", "Chain-of-thought verification, meta-evaluation, self-correction loops")
        Container(adk, "Google ADK DS Team", "Python / ADK + Vertex", "Hypothesis, CausalInference, FeatureEngineering, ModelTraining agents")
    }

    Container_Boundary(mcp_layer, "FastMCP Tool Servers") {
        Container(mcp_python, "mcp-python-sandbox", "Go/Python", "Secure code execution, NLI faithfulness scorer, structured output")
        Container(mcp_sql, "mcp-sql-executor", "Go", "NL-to-SQL, query execution, numerical verification")
        Container(mcp_viz, "mcp-visualization", "Node.js", "25+ chart types via ECharts/D3.js/deck.gl")
        Container(mcp_kb, "mcp-knowledge-base", "Python", "MMR RAG, hybrid retrieval, GraphRAG, temporal grounding")
        Container(mcp_report, "mcp-report-generator", "Python", "Narrative generation, PDF/PPTX, Merkle provenance, IPFS anchoring")
        Container(mcp_dbt, "mcp-dbt-runner", "Python", "dbt model execution, lineage, data contracts")
        Container(mcp_connector, "mcp-data-connector", "Go", "80+ source connectors, CDC, Kafka publishing")
    }

    Container_Boundary(inference_layer, "AI Inference Layer") {
        Container(vllm, "vLLM Server", "Python/CUDA", "Local 70B/32B models, speculative decoding, PagedAttention")
        Container(ollama, "Ollama SLM", "Go", "Phi-3.5-mini, Gemma-2-2B — intent classify, complexity score")
        Container(slm_router, "SLM Router", "Python", "Query routing logic: edge→SLM→cloud LLM→RLM tier escalation")
        Container(cf_workers, "Cloudflare Workers AI", "JS/WASM", "Edge inference at 300+ PoPs — Llama 3.2 3B, Phi-3.5-mini")
    }

    Container_Boundary(data_layer, "Data & Storage Layer") {
        ContainerDb(postgres, "PostgreSQL 16", "pgvector + TimescaleDB", "Tenant data, agent memory, metadata, audit logs")
        ContainerDb(clickhouse, "ClickHouse", "OLAP", "Analytics queries, materialised views, Langfuse traces")
        ContainerDb(qdrant, "Qdrant", "Vector DB", "Embeddings, MMR retrieval, worker long-term memory")
        ContainerDb(redis, "Redis 7", "Cache", "Session state, query result cache (60s TTL), rate limiting")
        ContainerDb(kafka, "Apache Kafka", "Streaming", "Event bus — agent comms, CDC events, real-time ingestion")
        ContainerDb(minio, "MinIO / S3", "Object Storage", "Raw files, model artifacts, Iceberg table data, reports")
        ContainerDb(iceberg, "Apache Iceberg", "Lakehouse", "ACID table format on MinIO, time-travel, schema evolution")
        ContainerDb(neo4j, "Neo4j", "Graph DB", "GraphRAG entity graphs, data lineage DAG, knowledge graph")
        ContainerDb(mongo, "MongoDB", "Document DB", "Episodic agent memory, unstructured logs, event store")
    }

    Container_Boundary(observability, "Observability Stack") {
        Container(langfuse, "Langfuse", "Self-hosted", "LLM tracing, prompt versioning, eval scoring, cost analytics")
        Container(otel, "OpenTelemetry Collector", "OTLP", "Unified telemetry collection → Jaeger, Prometheus, Loki")
        Container(grafana, "Grafana", "Dashboards", "Infrastructure + LLM SLO dashboards, SLA alerting")
        Container(flink, "Apache Flink", "Streaming", "Stateful CEP, sessionisation, Iceberg streaming sink, anomaly detection")
    }

    Rel(user, web, "HTTPS/WSS")
    Rel(web, kong, "HTTPS")
    Rel(kong, litellm, "gRPC/REST")
    Rel(kong, langgraph, "gRPC/REST")
    Rel(litellm, vllm, "REST")
    Rel(litellm, ollama, "REST")
    Rel(langgraph, crewai, "Python call")
    Rel(langgraph, autogen, "Python call")
    Rel(langgraph, adk, "Python call")
    Rel(crewai, mcp_python, "MCP protocol")
    Rel(crewai, mcp_sql, "MCP protocol")
    Rel(crewai, mcp_viz, "MCP protocol")
    Rel(crewai, mcp_kb, "MCP protocol")
    Rel(crewai, mcp_report, "MCP protocol")
    Rel(mcp_sql, clickhouse, "TCP")
    Rel(mcp_kb, qdrant, "gRPC")
    Rel(mcp_connector, kafka, "Kafka Producer")
    Rel(flink, iceberg, "Iceberg Sink")
    Rel(langfuse, clickhouse, "ClickHouse writer")
    Rel(otel, grafana, "OTLP")
```

---

## Level 2 — Technology Stack Map

```mermaid
graph TB
    subgraph FRONTEND["🖥️  Frontend (Next.js 15)"]
        NX[Next.js 15 App Router]
        TW[Tailwind v4 + shadcn/ui]
        EC[ECharts 5 + D3.js + deck.gl]
        AG[AG Grid Enterprise]
        MO[Monaco Editor]
        ZU[Zustand State]
        WL[WebLLM WASM/WebGPU]
    end

    subgraph GATEWAY["🔀  Gateway Layer"]
        KG[Kong 3.x API Gateway]
        LL[LiteLLM Proxy v1.x]
        LF[Langfuse SDK callbacks]
    end

    subgraph AGENTS["🤖  Agent Orchestration"]
        LG[LangGraph Orchestrator]
        CR[CrewAI Teams]
        AU[AutoGen CriticAgent]
        GK[Google ADK DS Team]
        SR[SLM Router — Phi-3.5-mini]
    end

    subgraph MCP["🔧  MCP Tool Servers"]
        MP[mcp-python-sandbox]
        MS[mcp-sql-executor]
        MV[mcp-visualization]
        MK[mcp-knowledge-base]
        MR[mcp-report-generator]
        MD[mcp-data-connector]
        MB[mcp-dbt-runner]
    end

    subgraph INFERENCE["⚡  LLM Inference Tiers"]
        VL[vLLM — 70B/32B local]
        OL[Ollama — SLMs local]
        CF[Cloudflare Workers AI]
        CL[Claude claude-sonnet-4-6 cloud]
        DS[DeepSeek-R1:32b RLM]
    end

    subgraph DATA["🗄️  Data & Storage"]
        PG[(PostgreSQL 16 + pgvector)]
        CH[(ClickHouse OLAP)]
        QD[(Qdrant Vector)]
        RD[(Redis 7 Cache)]
        KF[(Apache Kafka)]
        MN[(MinIO Object Store)]
        IC[(Apache Iceberg)]
        N4[(Neo4j Graph)]
        MG[(MongoDB)]
    end

    subgraph OBS["📊  Observability"]
        LFU[Langfuse Self-Hosted]
        OT[OpenTelemetry]
        GR[Grafana + Prometheus]
        JG[Jaeger Tracing]
        LK[Loki Logs]
    end

    FRONTEND --> GATEWAY --> AGENTS --> MCP --> DATA
    AGENTS --> INFERENCE
    MCP --> INFERENCE
    GATEWAY --> OBS
    AGENTS --> OBS
    MCP --> OBS
```
