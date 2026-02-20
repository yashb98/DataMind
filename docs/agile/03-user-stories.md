# User Stories — INVEST-Compliant Library

> **Format:** `As a [persona], I want to [action], so that [benefit].`
> **Criteria:** INVEST (Independent, Negotiable, Valuable, Estimable, Small, Testable)

---

## Persona Definitions

| Persona | Role | Primary Goal |
|---------|------|--------------|
| **Alex** | Business Analyst | Get data answers in natural language without writing SQL |
| **Sam** | Data Scientist | Train models and run experiments without infrastructure overhead |
| **Dana** | Data Engineer | Ingest and transform data reliably with full lineage |
| **Jordan** | Platform Admin | Manage tenants, workers, compliance, and costs |
| **Morgan** | CFO / Executive | Receive automated reports and monitor KPIs |
| **Riley** | DPO (Data Protection Officer) | Ensure GDPR compliance and handle DSR requests |

---

## EPIC 1 — Natural Language Analytics

### US-001
**As Alex**, I want to type a question in plain English (e.g. "What were our top 5 products by revenue in Q3?") and receive a bar chart with the correct SQL query shown, so that I don't need to know SQL to explore data.

**Acceptance Criteria:**
- Given: Alex types a NL query with valid data context
- When: Query is submitted via the NL query interface
- Then: SQL is generated, executed, and a bar chart is returned within 800ms (p50)
- And: The SQL query is displayed below the chart for transparency
- And: A Langfuse trace is created with eval score ≥ 0.8

**Story Points:** 8 | **Sprint:** 4

---

### US-002
**As Alex**, I want the AI to warn me when a retrieved insight might be stale (> 90 days old), so that I don't make business decisions on outdated data.

**Acceptance Criteria:**
- Given: A RAG chunk with `ingestion_date` > 90 days ago is used
- When: The response is generated
- Then: An amber warning "⚠️ Data from [date] — may be outdated" appears
- And: The warning links to the data source for refreshing

**Story Points:** 2 | **Sprint:** 5

---

### US-003
**As Alex**, I want every AI-generated insight to cite the exact data rows it was based on, so that I can verify the answer myself.

**Acceptance Criteria:**
- Given: An insight is generated from retrieved chunks
- When: The response is displayed
- Then: Each factual claim has a footnote linking to the source chunk ID
- And: Clicking the footnote shows the raw data row

**Story Points:** 3 | **Sprint:** 5

---

## EPIC 2 — Dashboard & Visualisation

### US-010
**As Alex**, I want to drag and drop charts onto a grid canvas and save the layout as a named dashboard, so that I can build a custom KPI view without asking for IT help.

**Acceptance Criteria:**
- Given: Alex has run at least 3 queries
- When: Alex opens the Dashboard Builder
- Then: Chart widgets can be dragged to a 12-column responsive grid
- And: Saving the dashboard persists it for the user's next session
- And: Dashboard loads in < 300ms (cached, p99)

**Story Points:** 8 | **Sprint:** 7

---

### US-011
**As Morgan**, I want to receive a PDF report every Monday morning with revenue performance, risk summary, and key anomalies, without logging into any tool, so that I stay informed with zero effort.

**Acceptance Criteria:**
- Given: Celery Beat trigger fires every Monday at 06:00
- When: Workforce Manager dispatches Echo + Aria + Luna workers
- Then: PDF report is emailed within 5 minutes
- And: PDF contains a Merkle provenance certificate proving the AI did not alter data
- And: All numbers in the report have been SQL-verified (Layer 8)

**Story Points:** 13 | **Sprint:** 12

---

## EPIC 3 — Data Engineering

### US-020
**As Dana**, I want to connect a PostgreSQL database as a data source using a wizard, and have the schema automatically detected and profiled, so that I can start analytics within 10 minutes.

**Acceptance Criteria:**
- Given: Dana provides a valid PostgreSQL connection string
- When: The connection is submitted
- Then: Schema Inference Agent detects all tables, columns, types, and row counts
- And: DataProfiling Agent generates statistical summaries for each column
- And: PII columns are automatically tagged by Presidio with confidence scores

**Story Points:** 8 | **Sprint:** 4

---

### US-021
**As Dana**, I want data quality checks to run automatically on every pipeline run, and for pipelines to pause if data quality drops below threshold, so that downstream analyses are always based on clean data.

**Acceptance Criteria:**
- Given: A Flink job writes a new batch to Iceberg
- When: Great Expectations DQ suite runs on the batch
- Then: If null_rate > 5% or schema_drift detected → pipeline pauses + Slack alert
- And: All DQ results are logged to Neo4j lineage graph

**Story Points:** 5 | **Sprint:** 6

---

## EPIC 4 — GDPR & Privacy

### US-030
**As Riley**, I want PII columns to be automatically detected and masked before being sent to any external LLM, so that our customers' personal data never leaves our infrastructure in readable form.

**Acceptance Criteria:**
- Given: A dataset containing email, name, and phone columns is ingested
- When: The DataCleaningAgent is invoked
- Then: Presidio detects PII columns with confidence > 0.8
- And: Format-preserving encryption is applied to all PII columns
- And: A `pii_columns` metadata record is written to PostgreSQL with column names + PII types

**Story Points:** 5 | **Sprint:** 4

---

### US-031
**As Riley**, I want a self-service SAR portal where users can submit a Subject Access Request and receive a JSON export of all their data within 24 hours, so that we comply with GDPR Article 15.

**Acceptance Criteria:**
- Given: A data subject submits an SAR with verified email
- When: The DSR automation service processes the request
- Then: All data in PostgreSQL, ClickHouse, Qdrant, MinIO, MongoDB, Neo4j is found
- And: A structured JSON report is generated and emailed within 24 hours
- And: A DSR ticket is created in Jira with 30-day SLA timer

**Story Points:** 8 | **Sprint:** 12

---

### US-032
**As Riley**, I want a data subject's data to be deleted from ALL storage systems within 72 hours of an erasure request, so that we comply with GDPR Article 17.

**Acceptance Criteria:**
- Given: A Right to Erasure request is verified and approved
- When: The erasure workflow executes
- Then: Data is deleted from PostgreSQL, ClickHouse, Qdrant, MinIO, MongoDB, Neo4j within 72h
- And: A completion certificate PDF is generated and emailed to the subject
- And: The deletion is logged in the audit trail (which is itself exempt from erasure)

**Story Points:** 8 | **Sprint:** 12

---

## EPIC 5 — Digital Labor

### US-040
**As Jordan**, I want to deploy a pre-configured "Aria — Senior Data Analyst" worker with one click, and have it immediately start responding to natural language analytics requests from my team, so that I don't need to configure any AI system manually.

**Acceptance Criteria:**
- Given: Jordan selects "Aria" from the Worker Marketplace
- When: Deploy is clicked
- Then: Aria is registered in the Worker Registry within 60 seconds
- And: Aria can respond to a test NL query within 30 seconds (SLA)
- And: Aria's KPI dashboard shows task_completion_rate, avg_latency, cost_today

**Story Points:** 5 | **Sprint:** 13

---

### US-041
**As Jordan**, I want a kill switch button that immediately pauses all Digital Workers, so that I can halt all autonomous AI operations instantly in case of an emergency.

**Acceptance Criteria:**
- Given: All Digital Workers are running tasks
- When: Jordan presses the Kill Switch in the Admin console
- Then: All workers receive a SIGTERM-equivalent graceful stop
- And: In-progress tasks complete their current step but do not start new steps
- And: No data corruption occurs (all writes committed or rolled back)
- And: Workers are in "PAUSED" state within 10 seconds

**Story Points:** 3 | **Sprint:** 13

---

## EPIC 6 — Data Science Workbench

### US-050
**As Sam**, I want to run AutoML on a dataset and get a leaderboard of trained models with SHAP explanations, so that I can deliver a production model without manually tuning hyperparameters.

**Acceptance Criteria:**
- Given: Sam provides a dataset (< 10k rows) and selects a target column
- When: AutoGluon training is triggered
- Then: A leaderboard of ≥ 5 models is shown within 5 minutes
- And: The best model has a SHAP waterfall chart for feature importance
- And: The model can be deployed as a BentoML REST endpoint with one click

**Story Points:** 8 | **Sprint:** 9

---

### US-051
**As Sam**, I want to generate a time-series forecast with confidence intervals and a plain-English explanation of contributing factors, so that I can present accurate forecasts to non-technical stakeholders.

**Acceptance Criteria:**
- Given: Sam provides a time-series column with ≥ 50 data points
- When: ForecastingAgent runs with high-stakes mode enabled
- Then: A forecast chart shows the prediction line with 80% and 95% confidence bands
- And: A narrative explains seasonality, trend, anomalies, and external factors
- And: The narrative is generated by DeepSeek-R1:32b (RLM tier) for quality
- And: 5-sample self-consistency is applied — confidence intervals reflect sample variance

**Story Points:** 8 | **Sprint:** 9

---

## EPIC 7 — LLM Observability

### US-060
**As Jordan**, I want to see a cost breakdown by agent, model, and tenant in a real-time dashboard, so that I can identify cost spikes before they impact the monthly bill.

**Acceptance Criteria:**
- Given: LiteLLM forwards all call metadata to Langfuse via callback
- When: Jordan opens the Langfuse cost dashboard
- Then: Per-agent, per-model, per-tenant costs are visible with daily granularity
- And: An alert fires in Slack if any agent exceeds 2x rolling 7-day average cost
- And: Token budget limits are enforced per agent role (Cleaner: 2k, Planner: 8k)

**Story Points:** 5 | **Sprint:** 7

---

### US-061
**As Jordan**, I want every system prompt used by agents to be versioned in Langfuse, so that I can A/B test prompt changes and roll back to previous versions without redeployment.

**Acceptance Criteria:**
- Given: A prompt is updated in Langfuse Prompt Management
- When: The next agent invocation occurs
- Then: The agent fetches the latest prompt version at runtime (no redeploy)
- And: 50% of traffic routes to version A, 50% to version B (A/B config)
- And: Quality scores are compared per prompt version in the Langfuse dashboard

**Story Points:** 5 | **Sprint:** 7

---

## Story Map — User Journey View

```
Alex's Journey:  Connect Data → Profile Data → Ask NL Query → View Dashboard → Export Report
                 US-020         US-020         US-001         US-010          US-011

Sam's Journey:   Connect Data → AutoML → Evaluate → Deploy Model → Monitor
                 US-020         US-050   US-050      US-051         US-060

Riley's Journey: Configure GDPR → Monitor PII → Handle DSR → Audit Compliance
                 US-030          US-030         US-031/032    US-060

Jordan's Journey: Deploy Workers → Monitor Workforce → Kill Switch → Cost Control
                  US-040          US-040              US-041         US-060/061
```
