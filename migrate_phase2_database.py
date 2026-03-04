#!/usr/bin/env python3
"""
AMEM Migration - Phase 2: Database Setup & Data Migration

This script:
1. Sets up PostgreSQL with pgvector
2. Creates database schema
3. Exports data from v1 (Markdown files)
4. Imports data to v2 (PostgreSQL)
5. Generates embeddings for all memories
"""
import asyncio
import asyncpg
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import argparse
import hashlib

# Configuration
DEFAULT_DB_URL = "postgresql://amem:amem@localhost/amem"
WORKSPACE = Path(os.getenv("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))

# SQL Schema
SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255),
    api_key_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Memories table with vector support
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    memory_type VARCHAR(32) NOT NULL DEFAULT 'fact',
    importance FLOAT DEFAULT 0.5,
    embedding VECTOR(768),
    is_shared BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_shared ON memories(is_shared) WHERE is_shared = TRUE;

-- Vector index for similarity search (using ivfflat for faster builds)
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
ON memories 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Graph entities
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    embedding VECTOR(768),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entities_agent ON entities(agent_id);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

-- Graph relationships
CREATE TABLE IF NOT EXISTS relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    source_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    target_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    relation_type VARCHAR(64) NOT NULL,
    strength FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(agent_id, source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_relations_agent ON relations(agent_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- Migration tracking
CREATE TABLE IF NOT EXISTS migration_status (
    id SERIAL PRIMARY KEY,
    phase VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    details JSONB DEFAULT '{}'
);
"""

class DatabaseManager:
    """Manages PostgreSQL database operations"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            self.db_url,
            min_size=5,
            max_size=20
        )
        print("✓ Connected to PostgreSQL")
    
    async def setup_schema(self):
        """Create database schema"""
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            print("✓ Database schema created")
    
    async def create_agent(self, agent_id: str, name: str = None) -> str:
        """Create an agent and return database ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agents (agent_id, name)
                VALUES ($1, $2)
                ON CONFLICT (agent_id) DO UPDATE
                SET updated_at = NOW()
                RETURNING id
                """,
                agent_id,
                name or agent_id
            )
            return str(row['id'])
    
    async def import_memory(self, agent_db_id: str, content: str, 
                           memory_type: str = 'fact',
                           importance: float = 0.5,
                           is_shared: bool = False,
                           created_at: datetime = None) -> str:
        """Import a single memory"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memories 
                (agent_id, content, memory_type, importance, is_shared, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                agent_db_id,
                content,
                memory_type,
                importance,
                is_shared,
                created_at or datetime.now()
            )
            return str(row['id'])
    
    async def update_embedding(self, memory_id: str, embedding: List[float]):
        """Update embedding for a memory"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE memories SET embedding = $1 WHERE id = $2",
                embedding,
                memory_id
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        async with self.pool.acquire() as conn:
            agents = await conn.fetchval("SELECT COUNT(*) FROM agents")
            memories = await conn.fetchval("SELECT COUNT(*) FROM memories")
            shared = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE is_shared = TRUE")
            with_embeddings = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
            )
            
            return {
                'agents': agents,
                'memories': memories,
                'shared_memories': shared,
                'with_embeddings': with_embeddings
            }
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()


class V1DataExporter:
    """Exports data from AMEM v1 (Markdown files)"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = workspace / "memory"
        self.memory_md = workspace / "MEMORY.md"
    
    def parse_memory_md(self) -> List[Dict]:
        """Parse MEMORY.md into individual memories"""
        memories = []
        
        if not self.memory_md.exists():
            return memories
        
        content = self.memory_md.read_text(encoding='utf-8')
        
        # Parse permanent memories
        # Format: ### [TYPE] Content
        import re
        pattern = r'### \[([A-Z]+)\] (.*?)(?=### \[|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for mem_type, mem_content in matches:
            memories.append({
                'content': mem_content.strip(),
                'type': mem_type.lower(),
                'tier': 'semantic',
                'importance': 0.8,
                'is_shared': True,  # Permanent memories are shared
                'source': 'MEMORY.md'
            })
        
        return memories
    
    def parse_daily_logs(self) -> Dict[str, List[Dict]]:
        """Parse daily log files"""
        logs = {}
        
        if not self.memory_dir.exists():
            return logs
        
        for log_file in sorted(self.memory_dir.glob("*.md"), reverse=True):
            date_str = log_file.stem
            content = log_file.read_text(encoding='utf-8')
            
            # Parse episodes from daily log
            episodes = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('- ') or line.startswith('* '):
                    episodes.append({
                        'content': line[2:],
                        'type': 'episode',
                        'tier': 'episodic',
                        'importance': 0.5,
                        'is_shared': False,
                        'source': str(log_file),
                        'date': date_str
                    })
            
            logs[date_str] = episodes
        
        return logs
    
    def export_all(self) -> Dict[str, Any]:
        """Export all v1 data"""
        print("Exporting v1 data...")
        
        # Get all agent directories
        agents = set()
        
        # Check for agent-specific directories
        for agent_dir in self.memory_dir.glob("*"):
            if agent_dir.is_dir():
                agents.add(agent_dir.name)
        
        # If no agents found, use 'default'
        if not agents:
            agents = {'default'}
        
        data = {
            'exported_at': datetime.now().isoformat(),
            'agents': {}
        }
        
        for agent_id in agents:
            print(f"  Processing agent: {agent_id}")
            
            # For now, all agents share the same memory files
            # In v2, they'll have proper isolation
            memories = self.parse_memory_md()
            logs = self.parse_daily_logs()
            
            # Flatten logs into memories
            for date, episodes in logs.items():
                for ep in episodes:
                    memories.append(ep)
            
            data['agents'][agent_id] = {
                'memory_count': len(memories),
                'memories': memories
            }
            
            print(f"    ✓ {len(memories)} memories")
        
        return data


class EmbeddingGenerator:
    """Generates embeddings for memories"""
    
    def __init__(self, provider: str = "hash"):
        self.provider = provider
        self._ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    
    async def generate(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts"""
        if self.provider == "hash":
            # Use hash-based fallback (deterministic but not semantic)
            return self._hash_embeddings(texts)
        
        elif self.provider == "ollama":
            return await self._ollama_embeddings(texts)
        
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _hash_embeddings(self, texts: List[str], dim: int = 768) -> List[List[float]]:
        """Generate deterministic hash-based embeddings"""
        import random
        
        embeddings = []
        for text in texts:
            # Use hash as seed for deterministic "embedding"
            h = hashlib.sha256(text.encode()).hexdigest()
            random.seed(int(h, 16))
            vec = [random.gauss(0, 1) for _ in range(dim)]
            # Normalize
            import math
            norm = math.sqrt(sum(x*x for x in vec))
            vec = [x/norm for x in vec]
            embeddings.append(vec)
        
        return embeddings
    
    async def _ollama_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama"""
        import aiohttp
        
        embeddings = []
        async with aiohttp.ClientSession() as session:
            for text in texts:
                try:
                    async with session.post(
                        f"{self._ollama_url}/api/embeddings",
                        json={
                            "model": "nomic-embed-text",
                            "prompt": text[:8192]  # Truncate if too long
                        },
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            embeddings.append(data['embedding'])
                        else:
                            # Fallback to hash
                            embeddings.append(self._hash_embeddings([text])[0])
                except Exception as e:
                    print(f"    Warning: Ollama failed for text: {e}")
                    embeddings.append(self._hash_embeddings([text])[0])
        
        return embeddings


async def main():
    parser = argparse.ArgumentParser(description='AMEM Phase 2: Database Migration')
    parser.add_argument('--db-url', default=DEFAULT_DB_URL, help='PostgreSQL connection URL')
    parser.add_argument('--workspace', type=Path, default=WORKSPACE, help='AMEM workspace directory')
    parser.add_argument('--export-only', action='store_true', help='Only export v1 data')
    parser.add_argument('--import-only', type=str, help='Import from JSON file')
    parser.add_argument('--skip-embeddings', action='store_true', help='Skip embedding generation')
    parser.add_argument('--embedding-provider', default='hash', choices=['hash', 'ollama'],
                       help='Embedding provider')
    args = parser.parse_args()
    
    print("=" * 60)
    print("AMEM Migration - Phase 2: Database Setup & Data Migration")
    print("=" * 60)
    print()
    
    # Step 1: Export v1 data
    exporter = V1DataExporter(args.workspace)
    
    if args.import_only:
        print(f"Loading export from: {args.import_only}")
        with open(args.import_only) as f:
            data = json.load(f)
    else:
        data = exporter.export_all()
        
        # Save export
        export_file = args.workspace / "v1_export.json"
        with open(export_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Export saved: {export_file}")
        
        if args.export_only:
            print("\nExport complete. Review the file and run again without --export-only")
            return
    
    print()
    
    # Step 2: Setup database
    db = DatabaseManager(args.db_url)
    
    try:
        await db.connect()
        await db.setup_schema()
        
        # Step 3: Import agents and memories
        print("\nImporting to PostgreSQL...")
        
        for agent_id, agent_data in data['agents'].items():
            print(f"\n  Agent: {agent_id}")
            
            # Create agent
            agent_db_id = await db.create_agent(agent_id)
            print(f"    ✓ Created agent (ID: {agent_db_id[:8]}...)")
            
            # Import memories
            memories = agent_data.get('memories', [])
            memory_ids = []
            
            for i, mem in enumerate(memories):
                memory_id = await db.import_memory(
                    agent_db_id=agent_db_id,
                    content=mem['content'],
                    memory_type=mem.get('type', 'fact'),
                    importance=mem.get('importance', 0.5),
                    is_shared=mem.get('is_shared', False),
                    created_at=datetime.fromisoformat(mem['date']) if 'date' in mem else None
                )
                memory_ids.append(memory_id)
                
                if (i + 1) % 100 == 0:
                    print(f"    Imported {i + 1}/{len(memories)} memories...")
            
            print(f"    ✓ Imported {len(memories)} memories")
            
            # Step 4: Generate embeddings
            if not args.skip_embeddings and memory_ids:
                print(f"    Generating embeddings ({args.embedding_provider})...")
                
                embed_gen = EmbeddingGenerator(args.embedding_provider)
                
                # Process in batches
                batch_size = 32
                for i in range(0, len(memories), batch_size):
                    batch = memories[i:i+batch_size]
                    batch_ids = memory_ids[i:i+batch_size]
                    
                    texts = [m['content'] for m in batch]
                    embeddings = await embed_gen.generate(texts)
                    
                    for mid, emb in zip(batch_ids, embeddings):
                        await db.update_embedding(mid, emb)
                    
                    if (i + batch_size) % 100 == 0:
                        print(f"      Processed {min(i + batch_size, len(memories))}/{len(memories)}...")
                
                print(f"    ✓ Generated {len(memories)} embeddings")
        
        # Step 5: Verify
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        
        stats = await db.get_stats()
        print(f"\nDatabase Statistics:")
        print(f"  Agents: {stats['agents']}")
        print(f"  Memories: {stats['memories']}")
        print(f"  Shared: {stats['shared_memories']}")
        print(f"  With embeddings: {stats['with_embeddings']}")
        
        print(f"\nNext steps:")
        print(f"  1. Verify data: psql {args.db_url} -c 'SELECT COUNT(*) FROM memories'")
        print(f"  2. Test search: psql {args.db_url} -c 'SELECT content FROM memories LIMIT 5'")
        print(f"  3. Continue to Phase 3: Dual-write setup")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
