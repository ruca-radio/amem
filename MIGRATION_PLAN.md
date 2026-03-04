# AMEM v1 → v2 Migration Plan

## Overview

This document provides a step-by-step migration path from AMEM v1 (prototype) to AMEM v2 (production).

**Timeline:** 5 weeks  
**Risk Level:** Medium (dual-write period reduces risk)  
**Rollback:** Possible at each phase

---

## Pre-Migration Checklist

- [ ] Review CRITICAL_REVIEW.md and understand all issues
- [ ] Set up staging environment
- [ ] Backup all v1 data
- [ ] Notify users of maintenance windows
- [ ] Prepare runbook for rollback procedures

---

## Phase 1: Security Hardening (Week 1)

**Goal:** Fix critical security vulnerabilities in v1 before migration

### Tasks

#### Day 1-2: Apply Security Patch
```bash
# 1. Download security patch
curl -o security_patch.py https://raw.githubusercontent.com/ruca-radio/amem/main/security_patch.py

# 2. Update amem_server.py to use security patch
# Add to top of amem_server.py:
from security_patch import SecurityManager, InputValidator, SafeErrorHandler

# 3. Set API keys
export AMEM_API_KEYS="claude:sk-xxx,gpt4:sk-yyy"
```

#### Day 3-4: Fix SQL Injection
```python
# In memory-api/main.py, replace:
agent_filter = f"AND agent_id = '{req.agent_id}'"

# With:
agent_filter = "AND agent_id = $1"
params = [req.agent_id]
# Then pass params to query
```

#### Day 5: Path Traversal Fix
```python
# In openclaw_memory.py, add:
from security_patch import PathSecurity

# Replace path construction with:
safe_path = PathSecurity.safe_path(WORKSPACE_DIR, path)
```

### Validation
- [ ] Run security tests
- [ ] Verify authentication blocks unauthorized access
- [ ] Test path traversal is blocked
- [ ] Confirm SQL injection attempts fail

### Rollback
```bash
# Simply revert to previous git commit
git checkout HEAD~1
```

---

## Phase 2: Database Setup & Data Migration (Week 2-3)

**Goal:** Set up PostgreSQL and migrate existing data

### Week 2: Infrastructure

#### Day 1-2: Deploy PostgreSQL
```bash
# Using Docker Compose
cat > docker-compose.db.yml << 'EOF'
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_USER: amem
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: amem
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
EOF

docker-compose -f docker-compose.db.yml up -d
```

#### Day 3-4: Initialize Schema
```bash
# Run schema migration
psql $DATABASE_URL -f migrations/001_initial_schema.sql
```

#### Day 5: Verify Database
```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Verify pgvector extension
psql $DATABASE_URL -c "SELECT * FROM pg_extension WHERE extname = 'vector'"
```

### Week 3: Data Migration

#### Day 1-2: Export v1 Data
```python
#!/usr/bin/env python3
# export_v1_data.py
import json
from pathlib import Path
from openclaw_memory import MemoryTools

def export_all_agents():
    workspace = Path.home() / ".openclaw" / "workspace"
    
    # Find all agent directories
    agents = []
    for agent_dir in (workspace / "memory").glob("*"):
        if agent_dir.is_dir():
            agents.append(agent_dir.name)
    
    all_data = {}
    for agent_id in agents:
        memory = MemoryTools(agent_id)
        stats = memory.store.stats()
        
        # Export all memories
        memories = []
        for tier in ["semantic", "episodic"]:
            results = memory.store.query("*", tiers=[tier], k=10000)
            for mem, score in results:
                memories.append({
                    "content": mem.content,
                    "type": mem.memory_type.value if hasattr(mem, 'memory_type') else "fact",
                    "tier": tier,
                    "importance": mem.importance,
                    "created_at": mem.created_at.isoformat() if hasattr(mem, 'created_at') else None
                })
        
        all_data[agent_id] = memories
        print(f"Exported {len(memories)} memories for {agent_id}")
    
    # Save to file
    with open("v1_export.json", "w") as f:
        json.dump(all_data, f, indent=2)
    
    return all_data

if __name__ == "__main__":
    export_all_agents()
```

#### Day 3-4: Import to v2
```python
#!/usr/bin/env python3
# import_to_v2.py
import json
import asyncio
import asyncpg
from datetime import datetime

async def import_memories():
    # Load exported data
    with open("v1_export.json") as f:
        data = json.load(f)
    
    # Connect to database
    conn = await asyncpg.connect("postgresql://amem:password@localhost/amem")
    
    for agent_id, memories in data.items():
        # Create agent if not exists
        agent_row = await conn.fetchrow(
            "INSERT INTO agents (agent_id, name) VALUES ($1, $1) ON CONFLICT (agent_id) DO UPDATE SET updated_at = NOW() RETURNING id",
            agent_id
        )
        agent_db_id = agent_row["id"]
        
        # Import memories
        for mem in memories:
            await conn.execute(
                """
                INSERT INTO memories (agent_id, content, memory_type, importance, is_shared, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                agent_db_id,
                mem["content"],
                mem["type"],
                mem["importance"],
                mem["tier"] == "semantic",
                datetime.fromisoformat(mem["created_at"]) if mem["created_at"] else datetime.now()
            )
        
        print(f"Imported {len(memories)} memories for {agent_id}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(import_memories())
```

#### Day 5: Verify Migration
```bash
# Count memories in v1 vs v2
python3 -c "
import json
with open('v1_export.json') as f:
    v1 = json.load(f)
v1_count = sum(len(m) for m in v1.values())
print(f'v1 total: {v1_count}')
"

psql $DATABASE_URL -c "SELECT COUNT(*) FROM memories"

# Should match!
```

### Validation
- [ ] All agents migrated
- [ ] Memory counts match
- [ ] Sample memories verified
- [ ] Embeddings regenerated (background job)

### Rollback
```bash
# Keep v1 files intact - no rollback needed
# Just don't use v2 yet
```

---

## Phase 3: Dual-Write Period (Week 4)

**Goal:** Run v1 and v2 in parallel, gradually shifting traffic

### Architecture

```
Client Request
     │
     ▼
┌─────────────┐
│  API Router │  ← Decides v1 or v2
│  (nginx)    │
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
v1 API   v2 API
 │         │
 │         ▼
 │    PostgreSQL
 │         │
 │    ┌────┘
 │    │
 ▼    ▼
Files (dual-write)
```

### Implementation

#### Day 1-2: Set Up API Router
```nginx
# nginx.conf
upstream v1_backend {
    server localhost:8080;
}

upstream v2_backend {
    server localhost:8000;
}

map $http_x_api_version $backend {
    default v1_backend;
    "2" v2_backend;
}

server {
    listen 80;
    
    location /api/ {
        proxy_pass http://$backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Day 3-4: Dual-Write Middleware
```python
# Add to v1 amem_server.py
# After successful write, also write to v2

async def dual_write_to_v2(agent_id: str, content: str, memory_type: str):
    """Write to v2 database for consistency during migration"""
    try:
        import asyncpg
        conn = await asyncpg.connect("postgresql://amem:password@localhost/amem")
        
        # Get agent_id from database
        row = await conn.fetchrow(
            "SELECT id FROM agents WHERE agent_id = $1",
            agent_id
        )
        if row:
            await conn.execute(
                "INSERT INTO memories (agent_id, content, memory_type) VALUES ($1, $2, $3)",
                row["id"], content, memory_type
            )
        
        await conn.close()
    except Exception as e:
        logger.error(f"Dual-write to v2 failed: {e}")
        # Don't fail v1 operation
```

#### Day 5: Gradual Traffic Shift
```bash
# Start with 10% traffic to v2
# Monitor error rates, latency

# If all good, increase:
# Day 6: 25%
# Day 7: 50%
```

### Monitoring
- [ ] Error rates comparable
- [ ] Latency acceptable
- [ ] Data consistency verified
- [ ] No data loss

### Rollback
```bash
# Route 100% traffic back to v1
# Fix issues
# Retry
```

---

## Phase 4: Full Cutover (Week 5)

**Goal:** Complete migration to v2, decommission v1

### Day 1-2: 100% v2 Traffic
```bash
# Update nginx to route all to v2
sed -i 's/default v1_backend;/default v2_backend;/' nginx.conf
nginx -s reload
```

### Day 3-4: Verify
- [ ] All clients working
- [ ] No v1 traffic
- [ ] Performance metrics good
- [ ] Error logs clean

### Day 5: Decommission v1
```bash
# Stop v1 server
pkill -f amem_server.py

# Archive v1 files (don't delete yet!)
tar czf amem_v1_backup_$(date +%Y%m%d).tar.gz ~/.openclaw/workspace/memory/

# Move to cold storage
aws s3 cp amem_v1_backup_*.tar.gz s3://amem-backups/v1-archive/

# Update documentation
# Notify users
```

---

## Post-Migration

### Week 6+: Optimization
- [ ] Background embedding generation for all memories
- [ ] Performance tuning
- [ ] Monitoring setup
- [ ] Documentation updates

### 30 Days Later
- [ ] Delete v1 backups (if confident)
- [ ] Archive migration scripts
- [ ] Post-mortem review

---

## Rollback Procedures

### Emergency Rollback (Data Loss Risk)
```bash
# 1. Stop v2
pkill -f "amem v2"

# 2. Restore v1
systemctl start amem-v1

# 3. Update DNS/router
# Point back to v1
```

### Graceful Rollback (No Data Loss)
```bash
# Only if dual-write was active
# 1. Sync any missing v2 data back to v1
python3 sync_v2_to_v1.py

# 2. Switch traffic
# 3. Keep v2 running read-only for verification
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data loss | Dual-write period, backups |
| Performance degradation | Gradual traffic shift, monitoring |
| Security issues | Phase 1 hardening |
| Extended downtime | Phased approach, rollback ready |
| Client incompatibility | API versioning, client updates |

---

## Success Criteria

- [ ] Zero data loss
- [ ] <5 minutes downtime per phase
- [ ] Search latency <20ms at 100k memories
- [ ] All security issues resolved
- [ ] 99.9% availability

---

## Timeline Summary

| Week | Phase | Key Deliverable |
|------|-------|-----------------|
| 1 | Security | Hardened v1 |
| 2 | Database | PostgreSQL running |
| 3 | Migration | Data in v2 |
| 4 | Dual-write | Gradual traffic shift |
| 5 | Cutover | Full v2 operation |

---

*Migration plan created: 2026-03-05*  
*Estimated effort: 5 weeks*  
*Risk: Medium*