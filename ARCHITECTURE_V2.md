# AMEM v2 Architecture Design

## Goals

1. **Security First** - Authentication, authorization, audit logging
2. **Production Ready** - Horizontal scaling, high availability
3. **Performance** - Sub-10ms search at 100k+ memories
4. **Data Integrity** - ACID transactions, point-in-time recovery
5. **Developer Experience** - Clean API, great docs, easy deployment

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Clients                               │
│  (Claude, GPT, Local LLMs, Web UI, CLI)                     │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS / WebSocket
┌────────────────────▼────────────────────────────────────────┐
│                   API Gateway (FastAPI)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Auth      │  │   Rate      │  │   Request   │         │
│  │   (JWT)     │  │   Limiting  │  │   Validation│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼─────┐ ┌────▼────┐ ┌────▼────┐
│   Memory    │ │  Graph  │ │  Embed  │
│   Service   │ │ Service │ │ Service │
│  (FastAPI)  │ │(FastAPI)│ │(FastAPI)│
└───────┬─────┘ └────┬────┘ └────┬────┘
        │            │           │
        └────────────┼───────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│              Data Layer                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ PostgreSQL  │  │    Redis    │  │  S3/MinIO   │         │
│  │  (pgvector) │  │   (Cache)   │  │  (Backups)  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | v1 (Current) | v2 (Target) | Reason |
|-----------|--------------|-------------|--------|
| Web Framework | ThreadingHTTPServer | FastAPI + uvicorn | Async, type-safe, auto-docs |
| Database | Markdown files | PostgreSQL + pgvector | ACID, vector search, scaling |
| Cache | None | Redis | Embedding cache, sessions, pub-sub |
| Vector Search | Linear scan O(n) | pgvector HNSW | O(log n) approximate search |
| Auth | None | JWT + API keys | Security |
| Deployment | Shell script | Docker + K8s | Production ready |
| Monitoring | None | Prometheus + Grafana | Observability |

---

## Database Schema (PostgreSQL)

```sql
-- Agents table
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255),
    api_key_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Memories table with vector support
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    importance FLOAT DEFAULT 0.5,
    embedding VECTOR(768),  -- pgvector extension
    is_shared BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP
);

-- Vector index for fast similarity search
CREATE INDEX ON memories 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Graph entities
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    embedding VECTOR(768),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Graph relationships
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    source_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(64) NOT NULL,
    strength FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audit log
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id UUID,
    details JSONB,
    ip_address INET,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## API Design (OpenAPI)

```yaml
openapi: 3.0.0
info:
  title: AMEM API
  version: 2.0.0

paths:
  /v2/auth/token:
    post:
      summary: Get JWT token
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                agent_id: {type: string}
                api_key: {type: string}
      responses:
        200:
          description: Token issued
          content:
            application/json:
              schema:
                type: object
                properties:
                  access_token: {type: string}
                  token_type: {type: string, enum: [Bearer]}
                  expires_in: {type: integer}

  /v2/memories:
    post:
      summary: Store a memory
      security:
        - bearerAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                content: {type: string, maxLength: 1000000}
                memory_type: {type: string, enum: [fact, preference, episode, skill]}
                importance: {type: number, minimum: 0, maximum: 1}
                scope: {type: string, enum: [shared, private], default: private}
      responses:
        201:
          description: Memory created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: string, format: uuid}
                  content: {type: string}
                  embedding_provider: {type: string}
                  created_at: {type: string, format: date-time}

    get:
      summary: Search memories
      security:
        - bearerAuth: []
      parameters:
        - name: q
          in: query
          schema: {type: string}
        - name: k
          in: query
          schema: {type: integer, default: 10, maximum: 100}
        - name: memory_type
          in: query
          schema: {type: string}
        - name: include_shared
          in: query
          schema: {type: boolean, default: true}
      responses:
        200:
          description: Search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  query: {type: string}
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        id: {type: string}
                        content: {type: string}
                        similarity: {type: number}
                        memory_type: {type: string}
                        source: {type: string, enum: [own, shared]}

  /v2/memories/{id}:
    delete:
      summary: Delete a memory (GDPR compliance)
      security:
        - bearerAuth: []
      responses:
        204:
          description: Deleted

  /v2/context:
    post:
      summary: Get context for prompt injection
      security:
        - bearerAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                query: {type: string}
                max_tokens: {type: integer, default: 1000}
                include_shared: {type: boolean, default: true}
      responses:
        200:
          description: Formatted context
          content:
            application/json:
              schema:
                type: object
                properties:
                  context: {type: string}
                  sources:
                    type: array
                    items:
                      type: object
                      properties:
                        memory_id: {type: string}
                        content: {type: string}
                        relevance: {type: number}

  /v2/graph/query:
    post:
      summary: Query graph relationships
      security:
        - bearerAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                entity: {type: string}
                relation_type: {type: string}
                depth: {type: integer, default: 1, maximum: 3}
      responses:
        200:
          description: Graph results

  /v2/health:
    get:
      summary: Health check
      responses:
        200:
          description: System health
          content:
            application/json:
              schema:
                type: object
                properties:
                  status: {type: string, enum: [healthy, degraded, unhealthy]}
                  components:
                    type: object
                    properties:
                      database: {type: string}
                      cache: {type: string}
                      embedding_service: {type: string}

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

---

## Service Architecture

### Memory Service
```python
# services/memory/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import aioredis

app = FastAPI(title="AMEM Memory Service")

# Dependencies
async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session

async def get_cache():
    return aioredis.from_url("redis://localhost")

async def get_current_agent(token: str = Depends(oauth2_scheme)):
    return verify_jwt(token)

# Endpoints
@app.post("/v2/memories", response_model=MemoryResponse)
async def create_memory(
    req: MemoryRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    cache: Redis = Depends(get_cache)
):
    # Get embedding (with caching)
    embedding = await get_embedding_cached(req.content, cache)
    
    # Store in database
    memory = Memory(
        agent_id=agent.id,
        content=req.content,
        embedding=embedding,
        ...
    )
    db.add(memory)
    await db.commit()
    
    # Audit log
    await audit_log.info(f"Memory created: {memory.id}")
    
    return MemoryResponse.from_orm(memory)

@app.get("/v2/memories")
async def search_memories(
    q: str,
    k: int = 10,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    # Get query embedding
    query_embedding = await get_embedding(q)
    
    # Vector search with pgvector
    results = await db.execute(
        select(Memory)
        .where(
            or_(
                Memory.agent_id == agent.id,
                Memory.is_shared == True
            )
        )
        .order_by(Memory.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    
    return SearchResults(results=results.scalars().all())
```

### Embedding Service
```python
# services/embedding/main.py
from fastapi import FastAPI
import httpx

app = FastAPI(title="AMEM Embedding Service")

# Connection pooling
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)

# LRU cache for embeddings
embedding_cache = LRUCache(maxsize=10000)

@app.post("/embed")
async def embed(texts: List[str]) -> List[List[float]]:
    # Check cache
    cached = []
    to_embed = []
    for text in texts:
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in embedding_cache:
            cached.append((text, embedding_cache[key]))
        else:
            to_embed.append(text)
    
    # Get embeddings for uncached
    if to_embed:
        embeddings = await call_ollama_batch(to_embed)
        for text, emb in zip(to_embed, embeddings):
            key = hashlib.sha256(text.encode()).hexdigest()
            embedding_cache[key] = emb
            cached.append((text, emb))
    
    return [emb for _, emb in sorted(cached, key=lambda x: texts.index(x[0]))]
```

---

## Deployment (Kubernetes)

```yaml
# k8s/memory-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: amem-memory
spec:
  replicas: 3
  selector:
    matchLabels:
      app: amem-memory
  template:
    metadata:
      labels:
        app: amem-memory
    spec:
      containers:
      - name: memory
        image: amem/memory:v2.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: amem-secrets
              key: database-url
        - name: REDIS_URL
          value: redis://redis:6379
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /v2/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /v2/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5

---
# k8s/postgres.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  template:
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg15
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi

---
# k8s/redis.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        args:
        - --maxmemory
        - 2gb
        - --maxmemory-policy
        - allkeys-lru
```

---

## Migration Path from v1

### Phase 1: Security Patch (Week 1)
- Apply `security_patch.py` to existing v1
- Add API key authentication
- Fix SQL injection
- Add input validation

### Phase 2: Database Migration (Week 2-3)
- Set up PostgreSQL + pgvector
- Export v1 data using backup.py
- Import to PostgreSQL
- Dual-write period (v1 files + v2 DB)

### Phase 3: API Transition (Week 4)
- Deploy v2 services alongside v1
- Update clients to use v2 API
- Gradual traffic shift

### Phase 4: Cleanup (Week 5)
- Remove v1 file-based storage
- Archive old files
- Full v2 operation

---

## Performance Targets

| Metric | v1 | v2 Target |
|--------|-----|-----------|
| Search latency (10k memories) | 50-200ms | <10ms |
| Search latency (100k memories) | 500ms-2s | <20ms |
| Write throughput | 10/sec | 1000/sec |
| Concurrent agents | 10 | 1000+ |
| Availability | N/A | 99.9% |
| RTO (Recovery Time) | N/A | <5 minutes |
| RPO (Data Loss) | Hours | <1 minute |

---

## Cost Estimate (AWS)

| Component | Instance | Monthly Cost |
|-----------|----------|--------------|
| EKS Cluster | 3x t3.medium | $150 |
| PostgreSQL | db.r6g.large | $200 |
| ElastiCache | cache.r6g.large | $150 |
| ALB | - | $20 |
| Storage | 100GB | $10 |
| **Total** | | **~$530/month** |

---

*Design completed: 2026-03-05*
*Next: Implementation planning*