-- Memory System Schema
-- Tiered memory with vector search, decay, and agent isolation

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Core memory table - all tiers
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Content
    content TEXT NOT NULL,
    embedding VECTOR(768),  -- nomic-embed-text dimension
    
    -- Metadata
    agent_id TEXT NOT NULL,           -- Which agent created/owns this
    session_id TEXT,                   -- Optional: tie to specific session
    memory_type TEXT NOT NULL,         -- 'fact', 'preference', 'episode', 'skill'
    
    -- Tiering
    tier TEXT NOT NULL DEFAULT 'episodic',  -- 'working', 'episodic', 'semantic'
    importance_score FLOAT DEFAULT 0.5,      -- 0-1, affects promotion/demotion
    
    -- Decay system
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 1,
    decay_factor FLOAT DEFAULT 1.0,          -- Multiplier for decay rate
    
    -- Alignment / versioning
    version INTEGER DEFAULT 1,
    superseded_by UUID REFERENCES memories(id),
    alignment_hash TEXT,                     -- For detecting drift
    
    -- Structured fields for filtering
    tags TEXT[],
    source TEXT,                             -- 'explicit', 'inferred', 'compressed'
    confidence FLOAT DEFAULT 1.0,
    
    -- Compression tracking
    original_ids UUID[],                     -- If this is a compressed summary
    compression_level INTEGER DEFAULT 0      -- How many generations of compression
);

-- Indexes for performance
CREATE INDEX idx_memories_agent ON memories(agent_id);
CREATE INDEX idx_memories_tier ON memories(tier);
CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_session ON memories(session_id);
CREATE INDEX idx_memories_accessed ON memories(last_accessed);
CREATE INDEX idx_memories_importance ON memories(importance_score DESC);

-- Vector search index (IVFFlat for balance of speed/recall)
CREATE INDEX idx_memories_embedding ON memories 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Working memory snapshots (ephemeral, per-session)
CREATE TABLE working_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    
    -- Compact representation of current context
    context_summary TEXT,
    active_memories UUID[],  -- References to semantic/episodic memories currently loaded
    
    -- Token budget management
    token_budget INTEGER DEFAULT 4000,
    current_usage INTEGER DEFAULT 0,
    
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_working_session ON working_memory(session_id);

-- Agent registry with capability profiles
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,     -- 'ollama', 'openai', 'anthropic', 'openrouter'
    model_name TEXT NOT NULL,
    
    -- Memory configuration per agent
    working_memory_tokens INTEGER DEFAULT 4000,
    episodic_retrieval_k INTEGER DEFAULT 10,
    semantic_retrieval_k INTEGER DEFAULT 5,
    
    -- Capability flags
    can_write_memory BOOLEAN DEFAULT true,
    can_compress BOOLEAN DEFAULT false,
    priority INTEGER DEFAULT 0,  -- For memory contention
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Memory operations log (for debugging, alignment verification)
CREATE TABLE memory_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation TEXT NOT NULL,     -- 'read', 'write', 'update', 'compress', 'decay'
    agent_id TEXT NOT NULL,
    session_id TEXT,
    memory_id UUID REFERENCES memories(id),
    
    -- Query context for reads
    query_embedding VECTOR(768),
    query_text TEXT,
    results_count INTEGER,
    
    -- Performance
    latency_ms INTEGER,
    tokens_used INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ops_agent ON memory_operations(agent_id);
CREATE INDEX idx_ops_session ON memory_operations(session_id);

-- Alignment checkpoints
CREATE TABLE alignment_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT,
    
    -- What was the intended behavior/preference
    expected TEXT NOT NULL,
    -- What actually happened
    actual TEXT NOT NULL,
    -- Gap analysis
    divergence_score FLOAT,
    
    -- Resolution
    corrected_memory_id UUID REFERENCES memories(id),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Views for convenient access

-- Active memories (not superseded, not fully decayed)
CREATE VIEW active_memories AS
SELECT * FROM memories 
WHERE superseded_by IS NULL 
  AND (tier != 'episodic' OR last_accessed > NOW() - INTERVAL '30 days');

-- Memory stats per agent
CREATE VIEW agent_memory_stats AS
SELECT 
    agent_id,
    tier,
    memory_type,
    COUNT(*) as count,
    AVG(importance_score) as avg_importance,
    MAX(last_accessed) as last_access
FROM memories
WHERE superseded_by IS NULL
GROUP BY agent_id, tier, memory_type;