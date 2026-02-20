# Sprint 01 Plan — Days 1 & 2: Foundation

> **Sprint Goal:** Runnable monorepo with all core infrastructure services healthy in Docker Compose.
> **Capacity:** 30 story points
> **Sprint Dates:** Day 1–2 of 28-day plan

---

## Sprint Goal Statement

> *"By end of Day 2, a developer can `docker compose up` and have all 14 infrastructure services running, Kong routing authenticated requests, LiteLLM proxying to Claude, and Langfuse capturing the first LLM trace."*

---

## Sprint Backlog

| # | Story ID | Title | Points | Assignee | Status |
|---|----------|-------|--------|----------|--------|
| 1 | E1-S1 | Turborepo monorepo scaffold | 3 | Dev | ✅ Done |
| 2 | E1-S2 | Docker Compose — 14 services | 5 | Dev | ✅ Done |
| 3 | E1-S3 | Kong API Gateway + JWT auth | 5 | Dev | 🔵 In Progress |
| 4 | E1-S4 | LiteLLM Proxy routing | 5 | Dev | ✅ Done |
| 5 | E1-S5 | Langfuse self-hosted + PostgreSQL | 5 | Dev | ✅ Done |
| 6 | E1-S6 | Apache Kafka 3-broker + Schema Registry | 5 | Dev | ✅ Done |
| 7 | E1-S7 | PostgreSQL 16 + pgvector + Timescale | 3 | Dev | ✅ Done |

**Total: 31 points**

---

## Day 1 Task Breakdown

### Morning Block (09:00–13:00)

| Task | Owner | Duration | Output |
|------|-------|----------|--------|
| `turbo init` + workspace setup (apps/, services/, packages/) | Dev | 45min | `package.json`, `turbo.json` |
| `.gitignore` + `.env.example` + pre-commit hooks | Dev | 30min | Config files |
| PostgreSQL 16 Docker service + init SQL (extensions, schemas) | Dev | 45min | `docker-compose.yml` postgres section |
| Redis 7 Sentinel config | Dev | 30min | Redis service + sentinel config |
| MinIO + Nessie Iceberg catalog | Dev | 45min | Object store running |
| Apache Kafka 3 brokers + Zookeeper + Schema Registry | Dev | 60min | Kafka topics created |

### Afternoon Block (14:00–18:00)

| Task | Owner | Duration | Output |
|------|-------|----------|--------|
| LiteLLM Proxy config (6 providers + Langfuse callback) | Dev | 60min | `litellm-config.yaml` |
| Langfuse Docker service (API + worker + ClickHouse) | Dev | 60min | Langfuse dashboard accessible |
| Kong Gateway Docker + JWT plugin + rate limiting | Dev | 90min | Routes working |
| OpenTelemetry Collector + Grafana + Prometheus | Dev | 60min | Metrics visible |
| Smoke test: `curl` Kong → LiteLLM → Claude, check Langfuse trace | Dev | 30min | First trace in Langfuse |

---

## Day 2 Task Breakdown

### Morning Block (09:00–13:00)

| Task | Owner | Duration | Output |
|------|-------|----------|--------|
| ClickHouse cluster + initial table schemas | Dev | 60min | ClickHouse responding |
| Qdrant + BAAI/bge-m3 embedding service | Dev | 60min | Vector search working |
| MongoDB for episodic memory | Dev | 30min | MongoDB healthy |
| Neo4j for graph RAG | Dev | 45min | Neo4j browser accessible |
| Ollama + Phi-3.5-mini + Gemma-2-2B pull | Dev | 45min | Models respond |

### Afternoon Block (14:00–18:00)

| Task | Owner | Duration | Output |
|------|-------|----------|--------|
| SLM Router service skeleton | Dev | 90min | Intent classifier returns label |
| `docker compose up --health-check` for all services | Dev | 30min | All 14 services healthy |
| GitHub Actions CI pipeline (lint + test + build) | Dev | 60min | CI passes on push |
| Sprint Review: demo Docker Compose boot to team | Dev | 30min | Sprint demo recorded |
| Sprint Retro + update backlog | Dev | 30min | Backlog refined |

---

## Sprint 01 Acceptance Criteria

- [ ] `docker compose up` starts all services with no errors
- [ ] `GET /health` returns 200 on all service health endpoints
- [ ] Kong routes `POST /api/llm/complete` → LiteLLM → Claude with JWT auth
- [ ] Langfuse shows trace with input_tokens, output_tokens, latency, model
- [ ] Kafka topic `raw.ingestion.test` can produce and consume messages
- [ ] PostgreSQL has schemas: `datamind_core`, `datamind_tenants`, `datamind_agents`
- [ ] ClickHouse has databases: `analytics`, `langfuse`
- [ ] Qdrant collection `knowledge_base` exists
- [ ] Ollama responds to `GET /api/tags` with phi3.5 and gemma2 listed
- [ ] CI pipeline completes in < 5 minutes

---

## Sprint 01 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Ollama model download slow (> 30min) | High | Low | Pull models async, continue other tasks |
| LiteLLM config error for one provider | Medium | Low | Test each provider independently |
| Docker memory limits on dev machine | Medium | Medium | Set `--memory 16g` compose profile |
| Kafka Zookeeper startup race condition | Low | Medium | Add `depends_on: condition: service_healthy` |
