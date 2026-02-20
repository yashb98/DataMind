# Component & Class Diagrams

> UML 2.5 Component and Class diagrams for each bounded domain.
> Rendered with Mermaid.

---

## 1. Agent Orchestration — Class Diagram

```mermaid
classDiagram
    class BaseAgent {
        <<abstract>>
        +String name
        +String role
        +List~Tool~ tools
        +AgentMemory memory
        +LLMConfig llm_config
        +AgentMetrics metrics
        +execute(task: Task) AgentResult
        +observe(event: Event) void
        +remember(key: str, value: Any) void
        +recall(key: str) Any
    }

    class DigitalWorker {
        +String worker_id
        +WorkerCapabilities capabilities
        +SLA sla
        +Float cost_per_task
        +WorkerStatus status
        +LangfuseClient tracer
        +execute(task: Task) WorkerResult
        +report_kpi() KPIReport
        +pause() void
        +resume() void
    }

    class WorkforceManager {
        +WorkerRegistry registry
        +LangGraphOrchestrator graph
        +GoalDecomposer decomposer
        +WorkloadBalancer balancer
        +assign(goal: BusinessGoal) WorkflowPlan
        +dispatch(task: Task) DigitalWorker
        +monitor() WorkforceDashboard
        +kill_switch() void
    }

    class LangGraphOrchestrator {
        +StateGraph graph
        +List~Node~ nodes
        +Dict~str,Edge~ edges
        +SLMRouter router
        +build_graph() StateGraph
        +run(state: AgentState) AgentState
        +add_node(name: str, fn: Callable) void
        +add_conditional_edge(src, fn, targets) void
    }

    class SLMRouter {
        +IntentClassifier intent_clf
        +ComplexityScorer complexity_scorer
        +SensitivityDetector sensitivity_detector
        +route(query: str) InferenceTier
        +classify_intent(query: str) IntentLabel
        +score_complexity(query: str) Float
        +detect_sensitivity(content: str) SensitivityLevel
    }

    class AntiHallucinationPipeline {
        +NLIScorer faithfulness_scorer
        +SelfConsistencySampler sampler
        +CriticAgent critic
        +StructuredOutputEnforcer enforcer
        +KnowledgeBoundaryDetector kb_detector
        +NumericalVerifier num_verifier
        +validate(response: LLMResponse, context: List~Chunk~) ValidationResult
    }

    class RAGRetriever {
        +QdrantClient vector_store
        +BM25Retriever sparse_retriever
        +ColBERTReranker reranker
        +Float mmr_lambda
        +retrieve(query: str, k: int) List~Chunk~
        +mmr_rerank(candidates: List~Chunk~, query: str) List~Chunk~
        +hybrid_search(query: str) List~Chunk~
    }

    class CryptographicProvenanceService {
        +SHA256Hasher hasher
        +MerkleTree evidence_tree
        +IPFSClient ipfs
        +hash_output(output: AgentOutput) ProvenanceRecord
        +build_merkle_tree(outputs: List~AgentOutput~) MerkleTree
        +anchor_to_ipfs(hash: str) CID
        +verify(record: ProvenanceRecord) bool
    }

    BaseAgent <|-- DigitalWorker
    BaseAgent <|-- IntakeAgent
    BaseAgent <|-- DataCleaningAgent
    BaseAgent <|-- NLToSQLAgent
    BaseAgent <|-- EDAAgent
    BaseAgent <|-- ForecastingAgent
    BaseAgent <|-- HypothesisAgent
    BaseAgent <|-- NarrativeAgent

    WorkforceManager --> LangGraphOrchestrator
    WorkforceManager --> DigitalWorker
    LangGraphOrchestrator --> SLMRouter
    LangGraphOrchestrator --> AntiHallucinationPipeline
    NLToSQLAgent --> RAGRetriever
    NarrativeAgent --> CryptographicProvenanceService
    EDAAgent --> AntiHallucinationPipeline
```

---

## 2. Data Pipeline — Component Diagram

```mermaid
graph LR
    subgraph INGESTION["📥  Ingestion Layer"]
        DC[mcp-data-connector\nGo service]
        PR[Presidio PII Scanner]
        FPE[FPE Masker\npyffx]
        KC[Kafka Producer]
    end

    subgraph PROCESSING["⚙️  Processing Layer"]
        FL[Apache Flink 1.19\nStateful CEP]
        SP[Apache Spark 3.5\nBatch ETL]
        DU[DuckDB\nIn-process OLAP]
        DBT[dbt Core\nTransformations]
    end

    subgraph STORAGE["🗄️  Storage Layer"]
        IC[(Apache Iceberg\nLakehouse)]
        CH[(ClickHouse\nOLAP)]
        TS[(TimescaleDB\nTime-Series)]
        MN[(MinIO\nObject Store)]
        QD[(Qdrant\nVector Store)]
        N4[(Neo4j\nLineage Graph)]
    end

    subgraph QUALITY["✅  Quality Layer"]
        GE[Great Expectations\nDQ Tests]
        MC[Monte Carlo Data\nObservability]
        OL[OpenLineage\nMarquez]
        EB[Schema Registry\nAvro/Protobuf]
    end

    subgraph SERVING["📤  Serving Layer"]
        AF[Arrow Flight RPC\nColumnar Transfer]
        MV[ClickHouse\nMaterialised Views]
        RC[Redis Cache\n60s TTL]
        WS[WebSocket\nLive Dashboards]
    end

    DC --> PR --> FPE --> KC
    KC --> FL
    KC --> SP
    FL --> IC
    FL --> TS
    SP --> IC
    IC --> DU
    IC --> CH
    DBT --> CH
    CH --> MV --> RC --> AF --> WS
    GE --> N4
    MC --> N4
    OL --> N4
    EB --> KC
```

---

## 3. LLM Inference Tiers — Component Diagram

```mermaid
graph TD
    Q[User Query] --> SR{SLM Router\nPhi-3.5-mini}

    SR -->|Confidence ≥ 0.85\nSimple intent| E[EDGE TIER\nCloudflare Workers AI\nWebLLM Browser]
    SR -->|Complexity = simple\nNon-sensitive| L[LOCAL SLM TIER\nOllama Phi-3.5-mini\nGemma-2-2B\n< 100ms]
    SR -->|Complexity = medium\nStandard LLM| C[CLOUD LLM TIER\nLiteLLM Proxy\nClaude / GPT-4o / Gemini]
    SR -->|Complexity = complex\nReasoning required| R[RLM TIER\nvLLM DeepSeek-R1:32b\nQwQ-32B\no3-mini]

    E -->|First token < 20ms| RESP[Response]
    L -->|First token < 50ms| RESP
    C -->|First token < 300ms| RESP
    R -->|Chain-of-thought\nFirst token < 600ms| RESP

    RESP --> AHP[Anti-Hallucination\nPipeline]
    AHP --> LF[Langfuse\nTrace & Score]
    LF --> OUT[Validated Output]

    subgraph LITELLM["LiteLLM Proxy Config"]
        direction TB
        LL1[Claude claude-sonnet-4-6 — Primary]
        LL2[GPT-4o — Fallback]
        LL3[Gemini 1.5 Pro — Fallback]
        LL4[llama3.3:70b — Local]
        LL5[codestral:22b — SQL]
        LL6[deepseek-r1:32b — Reasoning]
    end
```

---

## 4. GDPR Privacy Architecture — Component Diagram

```mermaid
graph TB
    subgraph INGESTION_GDPR["Data Ingestion — Privacy Gate"]
        PI[Raw Data In] --> PS[Presidio PII Scanner]
        PS -->|PII Detected| FE[FPE Encryption\npyffx]
        PS -->|No PII| PASS[Pass Through]
        FE --> TAG[PII Metadata Tagging\nPostgreSQL]
        PASS --> TAG
    end

    subgraph PURPOSE["Purpose Binding Engine"]
        TAG --> PB{Purpose\nPolicy Check}
        PB -->|Allowed| PROC[Processing Proceeds]
        PB -->|Denied| BLOCK[Request Blocked\n+ Audit Log]
    end

    subgraph DSR["Data Subject Rights Automation"]
        SAR[SAR Portal\nArt. 15]
        ERA[Erasure Workflow\nArt. 17]
        POR[Portability Export\nArt. 20]
        REC[Rectification\nArt. 16]
        SAR --> SEARCH[Search All Stores\nPG + CH + Qdrant +\nMinIO + MongoDB + Neo4j]
        ERA --> DEL[Delete from All Stores\n72h SLA]
        POR --> EXPORT[JSON/CSV Export\nIncludes AI Inferences]
    end

    subgraph BREACH["Breach Detection"]
        FA[Flink Anomaly Detection\nAccess Pattern Monitor]
        FA -->|Spike Detected| IR[Incident Response\nWorkflow]
        IR --> NOTIF[DPA Notification\n72h Template]
    end

    subgraph RETENTION["Retention Automation"]
        CB[Celery Beat Jobs]
        CB -->|Analytics > 2yr| DEL2[Auto Delete]
        CB -->|LLM Traces > 1yr| DEL3[Auto Delete]
        CB -->|Audit > 5yr| HOLD[Legal Hold]
    end
```

---

## 5. Verifiable AI — Merkle Provenance Chain

```mermaid
graph TB
    A1[Agent Output 1\nDataConnectorAgent] -->|SHA-256| H1[Hash H1]
    A2[Agent Output 2\nCleaningAgent] -->|SHA-256| H2[Hash H2]
    A3[Agent Output 3\nEDAAgent] -->|SHA-256| H3[Hash H3]
    A4[Agent Output 4\nNarrativeAgent] -->|SHA-256| H4[Hash H4]

    H1 --> M1[Merkle Node\nHash H1+H2]
    H2 --> M1
    H3 --> M2[Merkle Node\nHash H3+H4]
    H4 --> M2

    M1 --> ROOT[Merkle Root\nReport Hash]
    M2 --> ROOT

    ROOT --> PG[(PostgreSQL\nAudit Trail)]
    ROOT --> IPFS[(IPFS / Pinata\nImmutable Anchor)]
    ROOT --> CERT[Verification Certificate\nAttached to Report PDF]

    style ROOT fill:#f0f,color:#fff
    style IPFS fill:#0af,color:#fff
```
