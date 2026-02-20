// DataMind MongoDB Initialisation — Day 2
// Collections, indexes, and TTL policies for episodic agent memory

db = db.getSiblingDB('datamind');

// ============================================================
// Episodic Memory — agent past task logs
// ============================================================
db.createCollection('episodic_memory', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['worker_id', 'tenant_id', 'episode_type', 'content', 'created_at'],
      properties: {
        worker_id:    { bsonType: 'string' },
        tenant_id:    { bsonType: 'string' },
        episode_type: { enum: ['task_completion', 'error', 'correction', 'user_feedback', 'handoff'] },
        content:      { bsonType: 'object' },
        importance:   { bsonType: 'double', minimum: 0, maximum: 1 },
        tags:         { bsonType: 'array' },
        created_at:   { bsonType: 'date' },
        expires_at:   { bsonType: ['date', 'null'] }
      }
    }
  }
});

db.episodic_memory.createIndex({ tenant_id: 1, worker_id: 1, created_at: -1 });
db.episodic_memory.createIndex({ tenant_id: 1, episode_type: 1 });
db.episodic_memory.createIndex({ tags: 1 });
// TTL index: auto-expire non-permanent memories (expires_at = null means keep forever)
db.episodic_memory.createIndex(
  { expires_at: 1 },
  { expireAfterSeconds: 0, partialFilterExpression: { expires_at: { $type: 'date' } } }
);

// ============================================================
// Agent Event Log — every tool call, state transition, handoff
// ============================================================
db.createCollection('agent_events');
db.agent_events.createIndex({ tenant_id: 1, task_id: 1 });
db.agent_events.createIndex({ tenant_id: 1, agent_name: 1, created_at: -1 });
db.agent_events.createIndex({ created_at: -1 }, { expireAfterSeconds: 31536000 }); // 1yr TTL

// ============================================================
// Workflow State — LangGraph checkpoints (async state persistence)
// ============================================================
db.createCollection('workflow_checkpoints', {
  capped: false
});
db.workflow_checkpoints.createIndex({ thread_id: 1, checkpoint_id: 1 }, { unique: true });
db.workflow_checkpoints.createIndex({ tenant_id: 1, created_at: -1 });
db.workflow_checkpoints.createIndex(
  { created_at: 1 },
  { expireAfterSeconds: 604800 } // 7-day TTL for in-progress workflows
);

// ============================================================
// Correction Log — user feedback fed back to fine-tuning
// ============================================================
db.createCollection('corrections');
db.corrections.createIndex({ tenant_id: 1, agent_name: 1 });
db.corrections.createIndex({ approved_for_training: 1, eval_score: -1 });
db.corrections.createIndex({ created_at: -1 });

// ============================================================
// Knowledge Base Documents (raw docs before Qdrant embedding)
// ============================================================
db.createCollection('kb_documents');
db.kb_documents.createIndex({ tenant_id: 1, kb_id: 1 });
db.kb_documents.createIndex({ tenant_id: 1, status: 1 });
db.kb_documents.createIndex({ 'metadata.source': 1 });

print('DataMind MongoDB: collections and indexes created ✓');
