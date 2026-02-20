# DataMind — System Architecture Documentation

> **Version:** V2.0 | **Methodology:** Agile / SOLID / Domain-Driven Design
> **Standard:** UML 2.5 (rendered via Mermaid), C4 Model, Arc42

---

## Table of Contents

| # | Document | Description |
|---|----------|-------------|
| 1 | [System Overview](./01-system-overview.md) | C4 Context + Container diagrams, tech stack |
| 2 | [Component Diagrams](./02-component-diagrams.md) | UML component & class diagrams per bounded domain |
| 3 | [Sequence Diagrams](./03-sequence-diagrams.md) | End-to-end interaction flows for key user journeys |
| 4 | [Data Flow & ERD](./04-data-flow.md) | Data pipeline flows, entity relationships, storage topology |
| 5 | [Deployment Diagram](./05-deployment-diagram.md) | Kubernetes, multi-cloud, edge topology |
| 6 | [SOLID Principles](./06-solid-principles.md) | How every SOLID principle is enforced across the codebase |
| 7 | [Process Mapping](./07-process-mapping.md) | BPMN-style process maps for all major platform workflows |

---

## Architecture Decision Records (ADRs)

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-001 | LangGraph as primary orchestration (over Autogen-only) | Accepted |
| ADR-002 | Qdrant as primary vector store (over Pinecone) | Accepted |
| ADR-003 | Iceberg + Nessie for lakehouse (over Delta Lake) | Accepted |
| ADR-004 | FastMCP for tool servers (over custom REST APIs) | Accepted |
| ADR-005 | LiteLLM proxy for unified LLM routing (over direct SDK calls) | Accepted |
| ADR-006 | vLLM for local inference (over TGI) | Accepted |
| ADR-007 | ClickHouse for analytics (over Druid) | Accepted |
| ADR-008 | Kong for API gateway (over Nginx/Caddy) | Accepted |
| ADR-009 | Turborepo monorepo (over Nx) | Accepted |
| ADR-010 | Next.js 15 App Router (over Pages Router) | Accepted |

---

## Architectural Qualities (ISO 25010)

| Quality | Target | Mechanism |
|---------|--------|-----------|
| **Performance** | p99 < 2s interactive | Speculative decoding, Redis cache, ClickHouse MV, Arrow Flight |
| **Availability** | 99.9% uptime | Active-active multi-cloud, KEDA auto-scale, circuit breakers |
| **Security** | SOC2 + GDPR + PQC | Presidio, mTLS, Vault, CRYSTALS-Kyber, Dilithium |
| **Reliability** | Zero hallucinated stats | 8-layer anti-hallucination, Merkle provenance, SQL verification |
| **Scalability** | 10k concurrent users | Kubernetes HPA/VPA, Kafka partitioning, KEDA event-driven |
| **Observability** | 100% trace coverage | Langfuse + OpenTelemetry + Prometheus + Loki + Jaeger |
| **Maintainability** | SOLID + DDD | Bounded contexts, interfaces over implementations, DI everywhere |
| **Portability** | AWS/GCP/Azure/On-Prem | Conductor policy engine, Terraform cross-cloud, Helm charts |
