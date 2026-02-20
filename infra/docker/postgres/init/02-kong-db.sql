-- DataMind PostgreSQL — Kong database bootstrap
-- Kong needs its own DB (separate from DataMind's datamind DB)
-- Migrations run automatically via the kong-migrations service

CREATE DATABASE kong OWNER datamind;

-- Nessie catalog tables also live in the datamind DB (handled by Nessie itself)
-- Grant datamind user access to both DBs
GRANT ALL PRIVILEGES ON DATABASE kong TO datamind;
GRANT ALL PRIVILEGES ON DATABASE datamind TO datamind;
GRANT ALL PRIVILEGES ON DATABASE langfuse TO datamind;
