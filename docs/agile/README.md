# DataMind — Agile Methodology & Sprint Planning

> **Framework:** Scrum + Kanban hybrid (Scrumban)
> **Sprint Length:** 2-day sprints (aligned to 28-day plan = 14 sprints)
> **Team Size:** 1 AI Engineering Lead + Digital Workers
> **Ceremonies:** Daily standup (async), Sprint Review, Sprint Retrospective

---

## Agile Manifesto Alignment

| Manifesto Value | DataMind Application |
|-----------------|---------------------|
| **Individuals and interactions** over processes | Agent teams communicate via structured handoff protocols, not rigid workflows |
| **Working software** over comprehensive documentation | Ship deployable containers each sprint — architecture docs live alongside code |
| **Customer collaboration** over contract negotiation | Tenant feedback loops via Langfuse evaluation scores drive backlog priority |
| **Responding to change** over following a plan | Hot-swap prompts via Langfuse without redeployment; feature flags for gradual rollout |

---

## Definition of Done (DoD)

Every user story is **Done** only when ALL of the following are true:

- [ ] Code written, peer-reviewed (or AI self-reviewed), and merged to `main`
- [ ] Unit tests written with ≥ 80% coverage on new code
- [ ] Integration test added for the happy path
- [ ] Docker image builds without errors
- [ ] Helm chart template updated (if new service)
- [ ] SOLID compliance verified (import-linter passes)
- [ ] Langfuse trace emitted for any LLM call
- [ ] API documentation updated (FastAPI auto-docs + README)
- [ ] Security scan passes (Snyk + Bandit)
- [ ] Performance: meets latency target from SLA table

---

## Definition of Ready (DoR)

A user story is **Ready** for sprint when:

- [ ] Story has a clear acceptance criterion
- [ ] Story is estimated in story points (1, 2, 3, 5, 8, 13)
- [ ] Dependencies identified and unblocked
- [ ] Technical approach agreed (no unknowns)
- [ ] GDPR impact assessed (if touches data)

---

## Sprint Velocity & Estimation

| Story Points | Complexity | Example |
|-------------|------------|---------|
| 1 | Trivial | Add Langfuse @observe decorator to one endpoint |
| 2 | Small | New ClickHouse materialised view |
| 3 | Medium | Implement new MCP tool |
| 5 | Large | New agent class + unit tests |
| 8 | Very Large | New service with Docker + Helm |
| 13 | Epic (split) | Full agent team implementation |

**Target velocity:** 20–30 points per 2-day sprint

---

## Documents

| # | Document | Contents |
|---|----------|----------|
| 1 | [Product Backlog](./01-product-backlog.md) | All 28 days as prioritised epics + stories |
| 2 | [Sprint 01 Plan](./02-sprint-01-plan.md) | Day 1–2 detailed tasks |
| 3 | [User Stories](./03-user-stories.md) | Full INVEST-compliant user story library |
