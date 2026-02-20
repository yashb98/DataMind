// DataMind Neo4j Initialisation — Day 2
// Constraints, indexes for GraphRAG and data lineage DAG

// ============================================================
// Uniqueness Constraints
// ============================================================
CREATE CONSTRAINT tenant_id_unique IF NOT EXISTS
FOR (t:Tenant) REQUIRE t.tenant_id IS UNIQUE;

CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS
FOR (d:Dataset) REQUIRE d.dataset_id IS UNIQUE;

CREATE CONSTRAINT worker_id_unique IF NOT EXISTS
FOR (w:DigitalWorker) REQUIRE w.worker_id IS UNIQUE;

CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task) REQUIRE t.task_id IS UNIQUE;

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE;

CREATE CONSTRAINT kb_chunk_id_unique IF NOT EXISTS
FOR (c:KBChunk) REQUIRE c.chunk_id IS UNIQUE;

// ============================================================
// Full-Text Indexes (for GraphRAG entity search)
// ============================================================
CREATE FULLTEXT INDEX entity_text_search IF NOT EXISTS
FOR (e:Entity) ON EACH [e.name, e.description, e.aliases];

CREATE FULLTEXT INDEX kb_chunk_search IF NOT EXISTS
FOR (c:KBChunk) ON EACH [c.content, c.source_title];

// ============================================================
// Property Indexes for Lineage Queries
// ============================================================
CREATE INDEX dataset_tenant IF NOT EXISTS
FOR (d:Dataset) ON (d.tenant_id);

CREATE INDEX task_tenant IF NOT EXISTS
FOR (t:Task) ON (t.tenant_id);

CREATE INDEX task_type IF NOT EXISTS
FOR (t:Task) ON (t.task_type);

// ============================================================
// Seed: Built-in relationship types documentation
// (Labels the graph schema for tooling / GraphRAG context)
// ============================================================
// Relationships used:
//   (Dataset)-[:PRODUCED_BY]->(Task)
//   (Task)-[:USES]->(Dataset)
//   (Task)-[:TRIGGERED_BY]->(Task)
//   (DigitalWorker)-[:EXECUTED]->(Task)
//   (Entity)-[:RELATED_TO {weight}]->(Entity)
//   (Entity)-[:MENTIONED_IN]->(KBChunk)
//   (KBChunk)-[:PART_OF]->(KBDocument)
//   (Dataset)-[:DERIVED_FROM]->(Dataset)    // Iceberg lineage
//   (Task)-[:DEPENDS_ON]->(Task)            // workflow DAG
