-- init-db.sql - Database initialization script
CREATE EXTENSION IF NOT EXISTS vector;

-- Create documents table with vector embeddings
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(384),
    source VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create metadata index
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN (metadata);

-- Create audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    query TEXT,
    response TEXT,
    security_status VARCHAR(50),
    confidence_score FLOAT,
    request_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_log_request_id ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_security_status ON audit_log(security_status);

-- Create query cache table (optional, if not using Redis)
CREATE TABLE IF NOT EXISTS query_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE,
    result TEXT,
    ttl TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_query_cache_ttl ON query_cache(ttl);

-- Grant permissions (security best practice)
GRANT CONNECT ON DATABASE aegis_rag TO aegis_admin;
GRANT USAGE ON SCHEMA public TO aegis_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO aegis_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO aegis_admin;

-- Sample data for testing
INSERT INTO documents (content, source, metadata) VALUES 
    ('AegisRAG is an advanced RAG system with adversarial-resistant guardrails.', 'system', '{"type": "documentation", "version": "2.0"}'),
    ('The system uses LSTM-based threat detection for security.', 'system', '{"type": "documentation", "version": "2.0"}'),
    ('PostgreSQL with pgvector enables semantic similarity search.', 'system', '{"type": "documentation", "version": "2.0"}')
ON CONFLICT DO NOTHING;
