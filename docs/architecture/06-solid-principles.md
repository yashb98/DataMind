# SOLID Principles — DataMind Implementation Guide

> Every module, service, and agent in DataMind must adhere to these five principles.
> This document provides concrete examples from the DataMind codebase.

---

## S — Single Responsibility Principle (SRP)

> *"A class/module should have only one reason to change."*

### Applied Across DataMind

| Component | Single Responsibility | What It Does NOT Do |
|-----------|----------------------|---------------------|
| `NLToSQLAgent` | Convert natural language to SQL | Does not execute SQL, does not visualise |
| `mcp-sql-executor` | Execute SQL and return DataFrames | Does not generate SQL, does not ingest data |
| `mcp-visualization` | Render charts from data | Does not query data, does not generate narrative |
| `PresidioPIIScanner` | Detect PII in data | Does not mask, does not store metadata |
| `FPEMasker` | Mask PII with format-preserving encryption | Does not detect PII, does not manage keys |
| `LangfuseTracer` | Record traces and spans | Does not evaluate outputs, does not manage prompts |
| `CryptographicProvenanceService` | Hash outputs and build Merkle tree | Does not generate outputs, does not store to IPFS directly |
| `DSRAutomationService` | Handle data subject rights requests | Does not handle consent, does not handle breach notification |

### Code Structure Enforcing SRP

```
services/
├── pii/
│   ├── scanner.py          # ONLY: PII detection via Presidio
│   ├── masker.py           # ONLY: FPE masking via pyffx
│   └── metadata_store.py   # ONLY: PII column tagging to PostgreSQL
├── provenance/
│   ├── hasher.py           # ONLY: SHA-256 hashing of outputs
│   ├── merkle.py           # ONLY: Merkle tree construction
│   └── ipfs_anchor.py      # ONLY: IPFS publishing via Pinata
├── dsr/
│   ├── sar_handler.py      # ONLY: Subject Access Requests
│   ├── erasure_handler.py  # ONLY: Right to Erasure workflow
│   └── portability.py      # ONLY: Data export generation
```

---

## O — Open/Closed Principle (OCP)

> *"Open for extension, closed for modification."*

### LLM Provider Extension — No Core Changes Required

```python
# interfaces/llm_provider.py — CLOSED to modification
from abc import ABC, abstractmethod
from typing import AsyncIterator

class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str: ...

    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    def get_cost(self, input_tokens: int, output_tokens: int) -> float: ...


# providers/anthropic_provider.py — OPEN for extension (new file)
class AnthropicProvider(LLMProvider):
    async def complete(self, prompt, **kwargs):
        return await self.client.messages.create(...)

# providers/openai_provider.py — OPEN for extension (new file)
class OpenAIProvider(LLMProvider):
    async def complete(self, prompt, **kwargs):
        return await self.client.chat.completions.create(...)

# providers/deepseek_provider.py — New provider, zero core changes
class DeepSeekProvider(LLMProvider):
    async def complete(self, prompt, **kwargs):
        return await self.vllm_client.generate(...)
```

### Anti-Hallucination Layer Extension

```python
# interfaces/validation_layer.py — CLOSED
from abc import ABC, abstractmethod

class ValidationLayer(ABC):
    @abstractmethod
    def validate(self, response: LLMResponse, context: list[Chunk]) -> ValidationResult: ...

# layers/nli_faithfulness.py — OPEN (extend, don't modify)
class NLIFaithfulnessLayer(ValidationLayer):
    def validate(self, response, context): ...

# layers/self_consistency.py — OPEN (new layer, no core changes)
class SelfConsistencyLayer(ValidationLayer):
    def validate(self, response, context): ...

# pipeline/anti_hallucination.py — CLOSED
class AntiHallucinationPipeline:
    def __init__(self, layers: list[ValidationLayer]):
        self.layers = layers  # Inject any combination of layers

    def validate(self, response, context):
        result = ValidationResult()
        for layer in self.layers:
            result.merge(layer.validate(response, context))
        return result
```

### MCP Tool Server Extension

```python
# interfaces/mcp_tool.py — CLOSED
class MCPTool(ABC):
    @abstractmethod
    def get_schema(self) -> ToolSchema: ...

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult: ...

# Adding new tool = new file only, no framework changes
# tools/quantum_optimizer_tool.py — NEW tool, zero framework modification
class QuantumOptimizerTool(MCPTool):
    def execute(self, params): ...
```

---

## L — Liskov Substitution Principle (LSP)

> *"Objects of a subtype must be substitutable for their base type without altering correctness."*

### Agent Hierarchy — LSP Compliant

```python
# Any DigitalWorker must be substitutable for BaseAgent
def run_task(agent: BaseAgent, task: Task) -> AgentResult:
    return agent.execute(task)  # Works for ALL agent subtypes

# All of these are valid substitutions:
run_task(Aria(), revenue_task)      # Senior Data Analyst Worker
run_task(EDAAgent(), analysis_task) # Specialist agent
run_task(Luna(), risk_task)         # Risk Analyst Worker

# LSP Guarantee: every subclass honours the contract:
# - execute() always returns AgentResult (never None)
# - execute() always emits a Langfuse trace span
# - execute() always honours max_retries from SLA
```

### Retriever Substitution

```python
class BaseRetriever(ABC):
    def retrieve(self, query: str, k: int) -> list[Chunk]:
        # Contract: always returns list of 0..k Chunks, never raises on empty
        ...

# All substitutable without breaking the RAG pipeline:
retriever: BaseRetriever = MMRQdrantRetriever(lambda_=0.7)  # Dense MMR
retriever: BaseRetriever = HybridBM25Retriever()            # Sparse
retriever: BaseRetriever = ColBERTReranker()                # Re-ranker
retriever: BaseRetriever = GraphRAGRetriever()              # Neo4j graph
```

---

## I — Interface Segregation Principle (ISP)

> *"Clients should not be forced to depend on interfaces they do not use."*

### Agent Interface Segregation

```python
# BAD — fat interface (violates ISP)
class IAgent(ABC):
    def execute(self): ...
    def train_model(self): ...    # Not all agents train models
    def generate_report(self): ...  # Not all agents write reports
    def execute_sql(self): ...    # Not all agents run SQL
    def send_email(self): ...     # Not all agents send emails


# GOOD — segregated interfaces (ISP compliant)
class IExecutable(ABC):
    def execute(self, task: Task) -> AgentResult: ...

class IModelTrainer(ABC):
    def train(self, dataset: Dataset, config: TrainConfig) -> MLModel: ...

class IReportWriter(ABC):
    def write_report(self, data: ReportData) -> Report: ...

class ISQLExecutor(ABC):
    def run_sql(self, query: str) -> DataFrame: ...

class INotifier(ABC):
    def notify(self, message: str, channel: str) -> None: ...


# Each agent only implements relevant interfaces
class AtlasDataScientist(IExecutable, IModelTrainer):
    def execute(self, task): ...
    def train(self, dataset, config): ...

class EchoReportWriter(IExecutable, IReportWriter, INotifier):
    def execute(self, task): ...
    def write_report(self, data): ...
    def notify(self, message, channel): ...
```

### MCP Tool Interface Segregation

```python
# Segregated tool interfaces — tools only implement what they need
class IReadable(ABC):
    def read(self, params: ReadParams) -> ReadResult: ...

class IWritable(ABC):
    def write(self, params: WriteParams) -> WriteResult: ...

class IExecutable(ABC):
    def execute(self, code: str) -> ExecutionResult: ...

class IStreamable(ABC):
    def stream(self, params: StreamParams) -> AsyncIterator[Chunk]: ...

# mcp-knowledge-base: only reads (not writable by agents directly)
class KnowledgeBaseTool(IReadable, IStreamable): ...

# mcp-python-sandbox: only executes (not readable/writable directly)
class PythonSandboxTool(IExecutable): ...

# mcp-data-connector: reads from external, writes to Kafka
class DataConnectorTool(IReadable, IWritable): ...
```

---

## D — Dependency Inversion Principle (DIP)

> *"High-level modules should not depend on low-level modules. Both should depend on abstractions."*

### LangGraph Orchestrator — DIP Compliant

```python
# HIGH-LEVEL module depends on abstractions, not concretions
class LangGraphOrchestrator:
    def __init__(
        self,
        llm_provider: LLMProvider,        # abstraction
        retriever: BaseRetriever,          # abstraction
        tracer: TracingProvider,           # abstraction
        validator: ValidationPipeline,     # abstraction
        tool_registry: ToolRegistry,       # abstraction
    ):
        self.llm = llm_provider
        self.retriever = retriever
        self.tracer = tracer
        self.validator = validator
        self.tools = tool_registry

    async def run(self, state: AgentState) -> AgentState:
        # Works with ANY implementation of each abstraction
        with self.tracer.span("orchestrator.run"):
            context = await self.retriever.retrieve(state.query)
            response = await self.llm.complete(state.query, context=context)
            validated = await self.validator.validate(response, context)
            return state.with_result(validated)


# Dependency Injection — wired at composition root (main.py / container.py)
def build_orchestrator() -> LangGraphOrchestrator:
    return LangGraphOrchestrator(
        llm_provider=LiteLLMProvider(config=settings.litellm),
        retriever=MMRQdrantRetriever(client=qdrant_client, lambda_=0.7),
        tracer=LangfuseTracer(client=langfuse_client),
        validator=AntiHallucinationPipeline(layers=[
            NLIFaithfulnessLayer(model="DeBERTa-v3-large"),
            SelfConsistencyLayer(n_samples=5),
            StructuredOutputLayer(schema_registry=pydantic_registry),
            NumericalVerificationLayer(sql_executor=sql_executor),
        ]),
        tool_registry=MCPToolRegistry.from_config(settings.mcp),
    )
```

### Dependency Injection Container (DI Wiring)

```python
# container.py — composition root
from dependency_injector import containers, providers

class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infrastructure
    postgres_pool  = providers.Singleton(create_pg_pool, dsn=config.postgres.dsn)
    qdrant_client  = providers.Singleton(QdrantClient, url=config.qdrant.url)
    redis_client   = providers.Singleton(Redis, url=config.redis.url)
    langfuse_client = providers.Singleton(Langfuse, **config.langfuse)

    # Abstractions → Concrete bindings
    llm_provider    = providers.Factory(LiteLLMProvider, config=config.litellm)
    retriever       = providers.Factory(MMRQdrantRetriever, client=qdrant_client)
    tracer          = providers.Factory(LangfuseTracer, client=langfuse_client)

    # Orchestrator — receives abstractions, not concretions
    orchestrator = providers.Factory(
        LangGraphOrchestrator,
        llm_provider=llm_provider,
        retriever=retriever,
        tracer=tracer,
    )
```

---

## SOLID Compliance Checklist

| Principle | Enforcement Mechanism | Automated Check |
|-----------|-----------------------|-----------------|
| **SRP** | Each module ≤ 1 reason to change. PR review gate. | `pylint` single-responsibility linter rule |
| **OCP** | Abstract base classes in `interfaces/`. No `if isinstance()` for dispatch. | `mypy --strict` catches missing ABC implementations |
| **LSP** | All subclasses honour `@abstractmethod` contracts. Integration tests per subtype. | `pytest` substitution tests per agent type |
| **ISP** | Max 3 interfaces per class. No fat interfaces (> 5 methods). | Custom `flake8` plugin counts interface methods |
| **DIP** | No `import ConcreteClass` in high-level modules. All wired via DI container. | `import-linter` enforces layered architecture, blocks upward deps |
