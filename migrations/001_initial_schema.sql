-- AMEM v2 Initial Schema Migration
-- Creates tables for agents, memories, entities, relations, and audit_log
-- Requires pgvector extension

-- Enable pgvector extension for vector storage
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- AGENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    api_key_hash VARCHAR(255),
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE agents IS 'Registered agents in the system';
COMMENT ON COLUMN agents.agent_id IS 'Unique external identifier for the agent';

CREATE INDEX IF NOT EXISTS idx_agents_agent_id ON agents(agent_id);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(is_active) WHERE is_active = TRUE;

-- ============================================
-- MEMORIES TABLE (with vector support)
-- ============================================
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    memory_type VARCHAR(32) NOT NULL DEFAULT 'fact',
    importance FLOAT DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    embedding VECTOR(768),  -- 768-dim embeddings (nomic-embed-text)
    is_shared BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    source VARCHAR(255),  -- Source file or system
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE  -- For TTL support
);

COMMENT ON TABLE memories IS 'Agent memories with vector embeddings';
COMMENT ON COLUMN memories.memory_type IS 'Type: fact, preference, episode, skill';
COMMENT ON COLUMN memories.embedding IS 'Vector embedding for similarity search';
COMMENT ON COLUMN memories.is_shared IS 'Whether memory is shared across agents';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_shared ON memories(is_shared) WHERE is_shared = TRUE;
CREATE INDEX IF NOT EXISTS idx_memories_expires ON memories(expires_at) WHERE expires_at IS NOT NULL;

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_memories_metadata ON memories USING GIN (metadata);

-- Vector index for similarity search using ivfflat (good for <100k vectors)
-- For larger datasets, consider migrating to hnsw index
CREATE INDEX IF NOT EXISTS idx_memories_embedding_ivf 
ON memories 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Alternative HNSW index (better for >100k vectors, slower build)
-- CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw 
-- ON memories 
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- ============================================
-- ENTITIES TABLE (Graph nodes)
-- ============================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,  -- person, place, concept, etc.
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(agent_id, name, entity_type)
);

COMMENT ON TABLE entities IS 'Knowledge graph entities';

CREATE INDEX IF NOT EXISTS idx_entities_agent ON entities(agent_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_metadata ON entities USING GIN (metadata);

-- ============================================
-- RELATIONS TABLE (Graph edges)
-- ============================================
CREATE TABLE IF NOT EXISTS relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(64) NOT NULL,  -- knows, works_with, located_in, etc.
    strength FLOAT DEFAULT 1.0 CHECK (strength >= 0 AND strength <= 1),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(agent_id, source_id, target_id, relation_type)
);

COMMENT ON TABLE relations IS 'Knowledge graph relationships between entities';

CREATE INDEX IF NOT EXISTS idx_relations_agent ON relations(agent_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_relations_metadata ON relations USING GIN (metadata);

-- ============================================
-- AUDIT LOG TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    action VARCHAR(64) NOT NULL,  -- create, read, update, delete, search
    resource_type VARCHAR(64) NOT NULL,  -- memory, entity, relation, agent
    resource_id UUID,
    details JSONB DEFAULT '{}',  -- Additional context
    ip_address INET,
    user_agent TEXT,
    session_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE audit_log IS 'Audit trail for all significant operations';

CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- Partition audit_log by month for better performance
-- (Requires PostgreSQL 10+ and setup in application)

-- ============================================
-- MIGRATION TRACKING TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS migration_status (
    id SERIAL PRIMARY KEY,
    version VARCHAR(32) NOT NULL UNIQUE,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE migration_status IS 'Track migration status';

CREATE INDEX IF NOT EXISTS idx_migration_version ON migration_status(version);
CREATE INDEX IF NOT EXISTS idx_migration_status ON migration_status(status);

-- ============================================
-- FUNCTIONS AND TRIGGERS
-- ============================================

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to all tables
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memories_updated_at BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_entities_updated_at BEFORE UPDATE ON entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_relations_updated_at BEFORE UPDATE ON relations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to increment access count
CREATE OR REPLACE FUNCTION increment_memory_access(mem_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE memories 
    SET access_count = access_count + 1, 
        last_accessed = NOW() 
    WHERE id = mem_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEWS
-- ============================================

-- Memory statistics view
CREATE OR REPLACE VIEW memory_stats AS
SELECT 
    a.agent_id,
    a.name as agent_name,
    COUNT(m.id) as total_memories,
    COUNT(m.id) FILTER (WHERE m.is_shared) as shared_memories,
    COUNT(m.id) FILTER (WHERE m.embedding IS NOT NULL) as with_embeddings,
    COUNT(m.id) FILTER (WHERE m.memory_type = 'fact') as facts,
    COUNT(m.id) FILTER (WHERE m.memory_type = 'preference') as preferences,
    COUNT(m.id) FILTER (WHERE m.memory_type = 'episode') as episodes,
    COUNT(m.id) FILTER (WHERE m.memory_type = 'skill') as skills,
    MIN(m.created_at) as oldest_memory,
    MAX(m.created_at) as newest_memory
FROM agents a
LEFT JOIN memories m ON a.id = m.agent_id
GROUP BY a.id, a.agent_id, a.name;

-- Entity relation graph view
CREATE OR REPLACE VIEW entity_graph AS
SELECT 
    e1.name as source_name,
    e1.entity_type as source_type,
    r.relation_type,
    r.strength,
    e2.name as target_name,
    e2.entity_type as target_type,
    a.agent_id
FROM relations r
JOIN entities e1 ON r.source_id = e1.id
JOIN entities e2 ON r.target_id = e2.id
JOIN agents a ON r.agent_id = a.id;

-- ============================================
-- INITIAL DATA
-- ============================================

-- Insert migration record
INSERT INTO migration_status (version, description, status, completed_at)
VALUES ('001_initial_schema', 'Initial schema with pgvector support', 'completed', NOW())
ON CONFLICT (version) DO UPDATE SET 
    status = 'completed',
    completed_at = NOW();

-- ============================================
-- GRANTS (if using non-superuser)
-- ============================================
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO amem_app;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO amem_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO amem_app;
