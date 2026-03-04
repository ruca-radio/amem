"""
Memory API - Core memory service
Handles CRUD, tier management, and retrieval for all agents

SECURITY FIXES APPLIED:
- Fixed SQL injection in query_memories (dynamic SQL building)
- Added input validation for all endpoints
- Added API key authentication
- Safe error handling (no stack traces to client)
"""
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Query, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator

app = FastAPI(title="Memory API", version="2.0.0-secure")
security = HTTPBearer()

# Config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://memory:memory@postgres:5432/memory")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding:8001/embed")
API_KEYS = os.getenv("AMEM_API_KEYS", "")  # Format: "agent1:key1,agent2:key2"
ALLOW_INSECURE_AUTH = os.getenv("AMEM_ALLOW_INSECURE_AUTH", "").lower() == "true"

# Parse API keys
_api_key_map = {}
if API_KEYS:
    for pair in API_KEYS.split(','):
        if ':' in pair:
            agent_id, key = pair.split(':', 1)
            _api_key_map[agent_id.strip()] = key.strip()

# Tier configuration
TIER_LIMITS = {
    "working": {"max_age_hours": 1, "max_count": 50},
    "episodic": {"max_age_days": 30, "max_count": 1000},
    "semantic": {"max_age_days": 365 * 10, "max_count": 10000}
}

VALID_TIERS = {"working", "episodic", "semantic"}
VALID_MEMORY_TYPES = {"fact", "preference", "episode", "skill", "note"}
VALID_SOURCES = {"explicit", "inferred", "compressed"}


# ============== Security Utilities ==============

def validate_agent_id(agent_id: str) -> str:
    """Validate agent_id format (alphanumeric, hyphens, underscores only)"""
    if not agent_id or len(agent_id) > 64:
        raise HTTPException(400, "Invalid agent_id: must be 1-64 characters")
    if not re.match(r'^[a-zA-Z0-9_-]+$', agent_id):
        raise HTTPException(400, "Invalid agent_id: only alphanumeric, hyphens, underscores allowed")
    return agent_id


def validate_content(content: str) -> str:
    """Validate memory content"""
    if not isinstance(content, str):
        raise HTTPException(400, "Content must be a string")
    if not content.strip():
        raise HTTPException(400, "Content cannot be empty")
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "Content too large (max 10MB)")
    return content


def validate_tags(tags: List[str]) -> List[str]:
    """Validate tags"""
    if not isinstance(tags, list):
        raise HTTPException(400, "Tags must be a list")
    if len(tags) > 100:
        raise HTTPException(400, "Too many tags (max 100)")
    for tag in tags:
        if not isinstance(tag, str):
            raise HTTPException(400, "Tags must be strings")
        if len(tag) > 100:
            raise HTTPException(400, "Tag too long (max 100 characters)")
    return tags


async def authenticate(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Authenticate request using API key"""
    token = credentials.credentials
    
    # Development mode - explicitly enabled only
    if not _api_key_map:
        if ALLOW_INSECURE_AUTH:
            return "default"
        raise HTTPException(401, "API authentication required: configure AMEM_API_KEYS")
    
    # Find agent by API key
    for agent_id, key in _api_key_map.items():
        import hmac
        if hmac.compare_digest(key, token):
            return agent_id
    
    raise HTTPException(401, "Invalid API key")


# ============== Pydantic Models ==============

class MemoryCreate(BaseModel):
    content: str
    agent_id: str
    session_id: Optional[str] = None
    memory_type: str = "episode"  # fact, preference, episode, skill
    tier: str = "episodic"  # working, episodic, semantic
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: List[str] = []
    source: str = "explicit"  # explicit, inferred, compressed
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        if not v or len(v) > 64:
            raise ValueError('agent_id must be 1-64 characters')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('agent_id must be alphanumeric with hyphens/underscores')
        return v
    
    @validator('memory_type')
    def validate_memory_type(cls, v):
        if v not in VALID_MEMORY_TYPES:
            raise ValueError(f'memory_type must be one of: {VALID_MEMORY_TYPES}')
        return v
    
    @validator('tier')
    def validate_tier(cls, v):
        if v not in VALID_TIERS:
            raise ValueError(f'tier must be one of: {VALID_TIERS}')
        return v
    
    @validator('source')
    def validate_source(cls, v):
        if v not in VALID_SOURCES:
            raise ValueError(f'source must be one of: {VALID_SOURCES}')
        return v
    
    @validator('tags')
    def validate_tags(cls, v):
        if len(v) > 100:
            raise ValueError('Too many tags (max 100)')
        for tag in v:
            if len(tag) > 100:
                raise ValueError('Tag too long (max 100 characters)')
        return v


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = None
    tags: Optional[List[str]] = None
    tier: Optional[str] = None
    
    @validator('tier')
    def validate_tier(cls, v):
        if v is not None and v not in VALID_TIERS:
            raise ValueError(f'tier must be one of: {VALID_TIERS}')
        return v
    
    @validator('tags')
    def validate_tags(cls, v):
        if v is not None:
            if len(v) > 100:
                raise ValueError('Too many tags (max 100)')
            for tag in v:
                if len(tag) > 100:
                    raise ValueError('Tag too long (max 100 characters)')
        return v


class MemoryRead(BaseModel):
    id: UUID
    content: str
    agent_id: str
    memory_type: str
    tier: str
    importance_score: float
    created_at: datetime
    last_accessed: datetime
    access_count: int
    tags: List[str]
    similarity: Optional[float] = None


class QueryRequest(BaseModel):
    query: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    tiers: List[str] = ["semantic", "episodic"]
    memory_types: Optional[List[str]] = None
    k: int = 10
    min_similarity: float = 0.7
    recency_boost: bool = True
    
    @validator('query')
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        if len(v) > 1000:
            raise ValueError('Query too long (max 1000 characters)')
        return v
    
    @validator('k')
    def validate_k(cls, v):
        if v < 1 or v > 100:
            raise ValueError('k must be between 1 and 100')
        return v
    
    @validator('tiers')
    def validate_tiers(cls, v):
        for tier in v:
            if tier not in VALID_TIERS:
                raise ValueError(f'tier must be one of: {VALID_TIERS}')
        return v
    
    @validator('memory_types')
    def validate_memory_types(cls, v):
        if v is not None:
            for mt in v:
                if mt not in VALID_MEMORY_TYPES:
                    raise ValueError(f'memory_type must be one of: {VALID_MEMORY_TYPES}')
        return v


class WorkingMemorySnapshot(BaseModel):
    session_id: str
    agent_id: str
    context_summary: str
    active_memory_ids: List[UUID]
    token_budget: int = Field(default=4000, ge=100, le=32000)
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or len(v) > 128:
            raise ValueError('session_id must be 1-128 characters')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('session_id must be alphanumeric with hyphens/underscores')
        return v
    
    @validator('agent_id')
    def validate_agent_id(cls, v):
        if not v or len(v) > 64:
            raise ValueError('agent_id must be 1-64 characters')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('agent_id must be alphanumeric with hyphens/underscores')
        return v


# Database pool
pool: Optional[asyncpg.Pool] = None


@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)


@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


async def get_embedding(text: str) -> List[float]:
    """Get embedding from embedding service"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(EMBEDDING_URL, json={"text": text}, timeout=30.0)
        resp.raise_for_status()
        return resp.json()["embedding"]


# ============== API Endpoints ==============

@app.post("/memories", response_model=MemoryRead)
async def create_memory(req: MemoryCreate, auth_agent: str = Depends(authenticate)):
    """Store a new memory with automatic embedding"""
    # Validate content
    validate_content(req.content)
    
    # Authorization check: agents can only create memories for themselves
    if req.agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Cannot create memories for other agents")
    
    embedding = await get_embedding(req.content)
    
    # Generate alignment hash for drift detection
    alignment_hash = hashlib.sha256(
        f"{req.agent_id}:{req.content}:{req.memory_type}".encode()
    ).hexdigest()[:16]
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO memories 
                (content, embedding, agent_id, session_id, memory_type, tier,
                 importance_score, tags, source, alignment_hash)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            req.content, embedding, req.agent_id, req.session_id,
            req.memory_type, req.tier, req.importance, req.tags,
            req.source, alignment_hash
        )
    
    return MemoryRead(**dict(row))


@app.post("/query", response_model=List[MemoryRead])
async def query_memories(req: QueryRequest, auth_agent: str = Depends(authenticate)):
    """
    Semantic search across memory tiers with intelligent ranking.
    Combines vector similarity, recency, importance, and access patterns.
    
    SECURITY FIX: Uses parameterized queries instead of dynamic SQL building
    """
    query_embedding = await get_embedding(req.query)
    
    # Build query parameters
    params = [query_embedding, req.min_similarity, req.k]
    param_idx = 4  # Next parameter index ($1, $2, $3 are used above)
    
    # Build tier filter using ANY (parameterized)
    tier_filter = "tier = ANY($4)"
    params.append(req.tiers)
    param_idx += 1
    
    # Build memory type filter using ANY (parameterized)
    type_filter = ""
    if req.memory_types:
        type_filter = f"AND memory_type = ANY(${param_idx})"
        params.append(req.memory_types)
        param_idx += 1
    
    # Build agent filter (parameterized)
    agent_filter = ""
    if req.agent_id:
        agent_filter = f"AND agent_id = ${param_idx}"
        params.append(req.agent_id)
        param_idx += 1
    
    # Build session boost (parameterized)
    session_boost = "0"
    if req.session_id:
        session_boost = f"CASE WHEN session_id = ${param_idx} THEN 0.1 ELSE 0 END"
        params.append(req.session_id)
        param_idx += 1
    
    # SECURITY FIX: No string interpolation in SQL - all values are parameterized
    sql = f"""
        SELECT 
            id, content, agent_id, memory_type, tier,
            importance_score, created_at, last_accessed, access_count, tags,
            1 - (embedding <=> $1) as similarity,
            -- Composite score: similarity + recency + importance
            (1 - (embedding <=> $1)) * 0.5 +
            {session_boost} +
            CASE 
                WHEN last_accessed > NOW() - INTERVAL '1 hour' THEN 0.2
                WHEN last_accessed > NOW() - INTERVAL '24 hours' THEN 0.1
                WHEN last_accessed > NOW() - INTERVAL '7 days' THEN 0.05
                ELSE 0
            END +
            importance_score * 0.2 as composite_score
        FROM memories
        WHERE superseded_by IS NULL
          AND {tier_filter}
          {type_filter}
          {agent_filter}
          AND 1 - (embedding <=> $1) >= $2
        ORDER BY composite_score DESC
        LIMIT $3
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        
        # Update access patterns
        memory_ids = [r["id"] for r in rows]
        if memory_ids:
            await conn.execute(
                """
                UPDATE memories 
                SET last_accessed = NOW(), 
                    access_count = access_count + 1
                WHERE id = ANY($1)
                """,
                memory_ids
            )
    
    return [MemoryRead(**dict(r)) for r in rows]


@app.get("/memories/{memory_id}", response_model=MemoryRead)
async def get_memory(memory_id: UUID, auth_agent: str = Depends(authenticate)):
    """Retrieve a specific memory by ID"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM memories WHERE id = $1", memory_id
        )
        if not row:
            raise HTTPException(404, "Memory not found")
        
        # Authorization check
        if row["agent_id"] != auth_agent and auth_agent != "default":
            raise HTTPException(403, "Access denied")
        
        # Update access
        await conn.execute(
            "UPDATE memories SET last_accessed = NOW(), access_count = access_count + 1 WHERE id = $1",
            memory_id
        )
    
    return MemoryRead(**dict(row))


@app.patch("/memories/{memory_id}", response_model=MemoryRead)
async def update_memory(memory_id: UUID, req: MemoryUpdate, auth_agent: str = Depends(authenticate)):
    """Update memory content or metadata"""
    updates = []
    values = []
    
    # Check ownership first
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT agent_id FROM memories WHERE id = $1", memory_id)
        if not existing:
            raise HTTPException(404, "Memory not found")
        if existing["agent_id"] != auth_agent and auth_agent != "default":
            raise HTTPException(403, "Access denied")
    
    if req.content is not None:
        validate_content(req.content)
        updates.append(f"content = ${len(values)+1}")
        values.append(req.content)
        # Re-embed if content changed
        embedding = await get_embedding(req.content)
        updates.append(f"embedding = ${len(values)+1}")
        values.append(embedding)
        updates.append("version = version + 1")
    
    if req.importance is not None:
        updates.append(f"importance_score = ${len(values)+1}")
        values.append(req.importance)
    
    if req.tags is not None:
        updates.append(f"tags = ${len(values)+1}")
        values.append(req.tags)
    
    if req.tier is not None:
        updates.append(f"tier = ${len(values)+1}")
        values.append(req.tier)
    
    if not updates:
        raise HTTPException(400, "No fields to update")
    
    values.append(memory_id)
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE memories SET {', '.join(updates)} WHERE id = ${len(values)} RETURNING *",
            *values
        )
        if not row:
            raise HTTPException(404, "Memory not found")
    
    return MemoryRead(**dict(row))


@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: UUID, auth_agent: str = Depends(authenticate)):
    """Soft delete by marking superseded"""
    async with pool.acquire() as conn:
        # Check ownership
        existing = await conn.fetchrow("SELECT agent_id FROM memories WHERE id = $1", memory_id)
        if not existing:
            raise HTTPException(404, "Memory not found")
        if existing["agent_id"] != auth_agent and auth_agent != "default":
            raise HTTPException(403, "Access denied")
        
        await conn.execute(
            "UPDATE memories SET superseded_by = id WHERE id = $1",
            memory_id
        )
    return {"deleted": True}


@app.post("/working-memory/snapshot")
async def save_working_memory(req: WorkingMemorySnapshot, auth_agent: str = Depends(authenticate)):
    """Save or update working memory for a session"""
    # Authorization check
    if req.agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Cannot save working memory for other agents")
    
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO working_memory (session_id, agent_id, context_summary, active_memories, token_budget, current_usage)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (session_id) DO UPDATE SET
                context_summary = EXCLUDED.context_summary,
                active_memories = EXCLUDED.active_memories,
                current_usage = EXCLUDED.current_usage,
                updated_at = NOW()
            """,
            req.session_id, req.agent_id, req.context_summary,
            req.active_memory_ids, req.token_budget,
            sum(len(str(m)) for m in req.active_memory_ids)  # Rough token estimate
        )
    return {"saved": True}


@app.get("/working-memory/{session_id}")
async def get_working_memory(session_id: str, auth_agent: str = Depends(authenticate)):
    """Retrieve working memory for a session"""
    # Validate session_id
    if not session_id or len(session_id) > 128:
        raise HTTPException(400, "Invalid session_id")
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise HTTPException(400, "Invalid session_id format")
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM working_memory WHERE session_id = $1",
            session_id
        )
        if not row:
            raise HTTPException(404, "Working memory not found")
        
        # Authorization check
        if row["agent_id"] != auth_agent and auth_agent != "default":
            raise HTTPException(403, "Access denied")
    
    return dict(row)


@app.post("/agents/register")
async def register_agent(agent: dict, auth_agent: str = Depends(authenticate)):
    """Register a new agent with memory configuration"""
    # Validate required fields
    if "id" not in agent or "name" not in agent:
        raise HTTPException(400, "Missing required fields: id, name")
    
    agent_id = validate_agent_id(agent["id"])
    
    # Authorization check
    if agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Cannot register agents for other agents")
    
    # Validate provider and model_name if present
    provider = agent.get("provider", "")
    model_name = agent.get("model_name", "")
    if provider and len(provider) > 100:
        raise HTTPException(400, "Provider name too long")
    if model_name and len(model_name) > 100:
        raise HTTPException(400, "Model name too long")
    
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agents (id, name, provider, model_name, working_memory_tokens,
                              episodic_retrieval_k, semantic_retrieval_k, can_write_memory)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                provider = EXCLUDED.provider,
                model_name = EXCLUDED.model_name
            """,
            agent_id, agent["name"], provider, model_name,
            min(max(agent.get("working_memory_tokens", 4000), 100), 32000),
            min(max(agent.get("episodic_retrieval_k", 10), 1), 100),
            min(max(agent.get("semantic_retrieval_k", 5), 1), 100),
            bool(agent.get("can_write_memory", True))
        )
    return {"registered": True}


@app.get("/agents/{agent_id}")
async def get_agent_config(agent_id: str, auth_agent: str = Depends(authenticate)):
    """Get agent memory configuration"""
    agent_id = validate_agent_id(agent_id)
    
    # Authorization check
    if agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Access denied")
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM agents WHERE id = $1", agent_id)
        if not row:
            raise HTTPException(404, "Agent not found")
    return dict(row)


@app.get("/stats/{agent_id}")
async def get_agent_stats(agent_id: str, auth_agent: str = Depends(authenticate)):
    """Get memory statistics for an agent"""
    agent_id = validate_agent_id(agent_id)
    
    # Authorization check
    if agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Access denied")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM agent_memory_stats WHERE agent_id = $1",
            agent_id
        )
    return [dict(r) for r in rows]


@app.post("/alignment/check")
async def check_alignment(
    agent_id: str,
    expected: str,
    actual: str,
    auth_agent: str = Depends(authenticate)
):
    """Record an alignment checkpoint for drift detection"""
    agent_id = validate_agent_id(agent_id)
    
    # Authorization check
    if agent_id != auth_agent and auth_agent != "default":
        raise HTTPException(403, "Access denied")
    
    # Validate inputs
    validate_content(expected)
    validate_content(actual)
    
    # Simple divergence scoring based on embedding distance
    expected_emb = await get_embedding(expected)
    actual_emb = await get_embedding(actual)
    
    # Cosine similarity (simplified)
    import numpy as np
    similarity = np.dot(expected_emb, actual_emb) / (
        np.linalg.norm(expected_emb) * np.linalg.norm(actual_emb)
    )
    divergence = 1 - similarity
    
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO alignment_checkpoints (agent_id, expected, actual, divergence_score)
            VALUES ($1, $2, $3, $4)
            """,
            agent_id, expected, actual, divergence
        )
    
    return {"divergence": divergence, "aligned": divergence < 0.2}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0-secure"}
