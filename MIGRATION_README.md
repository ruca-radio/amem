# AMEM v1 to v2 Database Migration

This directory contains the Phase 2 migration scripts for moving AMEM from file-based storage (v1) to PostgreSQL with pgvector (v2).

## Files

| File | Description |
|------|-------------|
| `migrations/001_initial_schema.sql` | PostgreSQL schema with pgvector extension |
| `migrate_v1_to_v2.py` | Main migration script |
| `docker-compose.db.yml` | Docker Compose for PostgreSQL + Redis |
| `test_migration.py` | Test suite for migration logic |

## Prerequisites

- Python 3.8+
- PostgreSQL 15+ with pgvector extension (or Docker)
- Redis 7+ (optional, for caching)
- `asyncpg` and `aiohttp` Python packages

## Quick Start

### 1. Install Dependencies

```bash
pip install asyncpg aiohttp
```

### 2. Start PostgreSQL and Redis

Using Docker:

```bash
docker compose -f docker-compose.db.yml up -d
```

Or use your own PostgreSQL instance with pgvector installed:

```bash
# Install pgvector extension
psql -d amem -c "CREATE EXTENSION vector;"
```

### 3. Run Migration

```bash
# Full migration (export + import + embeddings)
python3 migrate_v1_to_v2.py

# Or step by step:

# Step 1: Export only
python3 migrate_v1_to_v2.py --export-only

# Step 2: Import from export file
python3 migrate_v1_to_v2.py --import-only v1_export.json

# Step 3: Verify
python3 migrate_v1_to_v2.py --verify-only
```

## Migration Options

```
usage: migrate_v1_to_v2.py [-h] [--db-url DB_URL] [--workspace WORKSPACE]
                           [--export-only] [--import-only FILE]
                           [--skip-embeddings] [--verify-only]
                           [--embedding-provider {hash,ollama}]
                           [--ollama-url OLLAMA_URL] [-v]

AMEM v1 to v2 Migration Script

optional arguments:
  -h, --help            show this help message and exit
  --db-url DB_URL       PostgreSQL connection URL
  --workspace WORKSPACE AMEM workspace directory
  --export-only         Only export v1 data
  --import-only FILE    Import from JSON file
  --skip-embeddings     Skip embedding generation
  --verify-only         Only verify existing migration
  --embedding-provider {hash,ollama}
                        Embedding provider (hash=deterministic fallback,
                        ollama=semantic)
  --ollama-url OLLAMA_URL
                        Ollama API endpoint
  -v, --verbose         Verbose output
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://amem:amem@localhost/amem` | PostgreSQL connection string |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `OPENCLAW_WORKSPACE` | `~/.openclaw/workspace` | AMEM workspace directory |

## Database Schema

The migration creates the following tables:

- **agents** - Registered agents
- **memories** - Agent memories with vector embeddings (768-dim)
- **entities** - Knowledge graph nodes
- **relations** - Knowledge graph edges
- **audit_log** - Audit trail for operations
- **migration_status** - Migration tracking

### Vector Search

Memories are stored with 768-dimensional embeddings for similarity search:

```sql
-- Find similar memories
SELECT content, embedding <=> query_embedding AS distance
FROM memories
WHERE agent_id = 'some-uuid'
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

## Embedding Providers

### Hash-based (Default)

Deterministic embeddings based on content hash. Fast, no external dependencies, but not semantically meaningful.

```bash
python3 migrate_v1_to_v2.py --embedding-provider hash
```

### Ollama (Recommended)

Semantic embeddings using nomic-embed-text model. Requires Ollama running.

```bash
# Start Ollama
ollama serve

# Pull embedding model
ollama pull nomic-embed-text

# Run migration with Ollama
python3 migrate_v1_to_v2.py --embedding-provider ollama
```

## Testing

Run the test suite:

```bash
python3 test_migration.py
```

Tests cover:
- Schema validation
- Memory type detection
- Data export
- Data transformation
- JSON serialization
- Embedding generation

## Troubleshooting

### Connection Refused

Ensure PostgreSQL is running:

```bash
docker compose -f docker-compose.db.yml ps
```

### pgvector Not Found

Install pgvector extension:

```bash
docker exec -it amem-postgres psql -U amem -c "CREATE EXTENSION vector;"
```

### Ollama Not Available

Migration will automatically fall back to hash-based embeddings if Ollama is not reachable.

### Verification Failed

Check the export file and database counts:

```bash
# Count memories in export
python3 -c "import json; d=json.load(open('v1_export.json')); print(sum(len(a['memories']) for a in d['agents'].values()))"

# Count memories in database
psql postgresql://amem:amem@localhost/amem -c "SELECT COUNT(*) FROM memories"
```

## Next Steps

After successful migration:

1. Verify data integrity: `python3 migrate_v1_to_v2.py --verify-only`
2. Test vector search with sample queries
3. Set up dual-write period (Phase 3)
4. Gradually shift traffic to v2

## Rollback

To rollback:

```bash
# Truncate all tables
docker exec -it amem-postgres psql -U amem -c "TRUNCATE memories, entities, relations, agents, audit_log CASCADE;"

# Re-run migration
python3 migrate_v1_to_v2.py
```

Original v1 files are preserved and not modified during migration.
