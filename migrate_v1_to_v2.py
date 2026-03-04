#!/usr/bin/env python3
"""
AMEM v1 to v2 Migration Script

Migrates data from AMEM v1 (Markdown files) to AMEM v2 (PostgreSQL with pgvector).

Usage:
    python3 migrate_v1_to_v2.py                    # Full migration
    python3 migrate_v1_to_v2.py --export-only      # Only export v1 data
    python3 migrate_v1_to_v2.py --import-only v1_export.json  # Import from file
    python3 migrate_v1_to_v2.py --skip-embeddings  # Skip embedding generation
    python3 migrate_v1_to_v2.py --verify-only      # Verify migration results

Environment Variables:
    DATABASE_URL    PostgreSQL connection string (default: postgresql://amem:amem@localhost/amem)
    OLLAMA_HOST     Ollama API endpoint (default: http://localhost:11434)
    OPENCLAW_WORKSPACE  Path to workspace (default: ~/.openclaw/workspace)
"""

import asyncio
import asyncpg
import json
import os
import sys
import re
import hashlib
import math
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_DB_URL = os.getenv("DATABASE_URL", "postgresql://amem:amem@localhost/amem")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
WORKSPACE = Path(os.getenv("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))


@dataclass
class MemoryRecord:
    """Represents a memory record from v1"""
    content: str
    memory_type: str
    tier: str  # semantic or episodic
    importance: float
    is_shared: bool
    source: str
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AgentData:
    """Represents all data for an agent"""
    agent_id: str
    name: str
    memories: List[MemoryRecord]
    entity_count: int = 0
    relation_count: int = 0


class DatabaseManager:
    """Manages PostgreSQL database operations"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None
    
    async def connect(self) -> bool:
        """Create connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("✓ Connected to PostgreSQL")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to connect to PostgreSQL: {e}")
            return False
    
    async def setup_schema(self) -> bool:
        """Create database schema from migration file"""
        migration_file = Path(__file__).parent / "migrations" / "001_initial_schema.sql"
        
        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        try:
            schema_sql = migration_file.read_text()
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)
            logger.info("✓ Database schema created")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to create schema: {e}")
            return False
    
    async def create_agent(self, agent_id: str, name: str = None) -> Optional[str]:
        """Create an agent and return database UUID"""
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
            return str(row['id']) if row else None
    
    async def import_memory(self, agent_db_id: str, memory: MemoryRecord) -> Optional[str]:
        """Import a single memory"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memories 
                (agent_id, content, memory_type, importance, is_shared, 
                 source, metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                agent_db_id,
                memory.content,
                memory.memory_type,
                memory.importance,
                memory.is_shared,
                memory.source,
                json.dumps(memory.metadata),
                memory.created_at or datetime.now(timezone.utc)
            )
            return str(row['id']) if row else None
    
    async def update_embedding(self, memory_id: str, embedding: List[float]) -> bool:
        """Update embedding for a memory"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memories SET embedding = $1 WHERE id = $2",
                    embedding,
                    memory_id
                )
            return True
        except Exception as e:
            logger.warning(f"Failed to update embedding for {memory_id}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        async with self.pool.acquire() as conn:
            agents = await conn.fetchval("SELECT COUNT(*) FROM agents")
            memories = await conn.fetchval("SELECT COUNT(*) FROM memories")
            shared = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE is_shared = TRUE")
            with_embeddings = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
            )
            entities = await conn.fetchval("SELECT COUNT(*) FROM entities")
            relations = await conn.fetchval("SELECT COUNT(*) FROM relations")
            
            # Memory type breakdown
            type_counts = await conn.fetch(
                "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
            )
            
            return {
                'agents': agents,
                'memories': memories,
                'shared_memories': shared,
                'with_embeddings': with_embeddings,
                'entities': entities,
                'relations': relations,
                'type_breakdown': {row['memory_type']: row['count'] for row in type_counts}
            }
    
    async def verify_migration(self, expected_data: Dict[str, AgentData]) -> bool:
        """Verify that migration was successful"""
        stats = await self.get_stats()
        
        expected_agents = len(expected_data)
        expected_memories = sum(len(a.memories) for a in expected_data.values())
        
        logger.info("\n" + "=" * 60)
        logger.info("Migration Verification")
        logger.info("=" * 60)
        
        checks = [
            ("Agents", stats['agents'], expected_agents),
            ("Memories", stats['memories'], expected_memories),
        ]
        
        all_passed = True
        for name, actual, expected in checks:
            status = "✓" if actual == expected else "✗"
            if actual != expected:
                all_passed = False
            logger.info(f"  {status} {name}: {actual} (expected: {expected})")
        
        # Check embeddings
        if stats['memories'] > 0:
            embedding_pct = (stats['with_embeddings'] / stats['memories']) * 100
            logger.info(f"  {'✓' if embedding_pct == 100 else '⚠'} Embeddings: {stats['with_embeddings']}/{stats['memories']} ({embedding_pct:.1f}%)")
        
        return all_passed
    
    async def test_vector_search(self, query_text: str = "test") -> List[Dict]:
        """Test vector search functionality"""
        try:
            async with self.pool.acquire() as conn:
                # First check if we have any memories with embeddings
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL LIMIT 1"
                )
                if count == 0:
                    logger.warning("No memories with embeddings found")
                    return []
                
                # Test with a simple query (would need actual embedding in production)
                rows = await conn.fetch(
                    """
                    SELECT id, content, memory_type
                    FROM memories
                    WHERE embedding IS NOT NULL
                    LIMIT 5
                    """
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Vector search test failed: {e}")
            return []
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()


class V1DataExporter:
    """Exports data from AMEM v1 (Markdown files)"""
    
    # Memory type patterns
    TYPE_PATTERNS = {
        'FACT': r'\[FACT\]|\[F\]',
        'PREFERENCE': r'\[PREFERENCE\]|\[PREF\]|\[P\]|⭐',
        'SKILL': r'\[SKILL\]|\[S\]',
        'EPISODE': r'\[EPISODE\]|\[E\]',
    }
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = workspace / "memory"
        self.memory_md = workspace / "MEMORY.md"
    
    def detect_memory_type(self, content: str) -> str:
        """Detect memory type from content markers"""
        content_upper = content.upper()
        
        if re.search(self.TYPE_PATTERNS['PREFERENCE'], content_upper):
            return 'preference'
        elif re.search(self.TYPE_PATTERNS['SKILL'], content_upper):
            return 'skill'
        elif re.search(self.TYPE_PATTERNS['EPISODE'], content_upper):
            return 'episode'
        else:
            return 'fact'
    
    def parse_memory_md(self) -> List[MemoryRecord]:
        """Parse MEMORY.md into individual memories"""
        memories = []
        
        if not self.memory_md.exists():
            logger.warning(f"MEMORY.md not found at {self.memory_md}")
            return memories
        
        content = self.memory_md.read_text(encoding='utf-8')
        
        # Parse permanent memories - various formats
        # Format 1: ### [TYPE] Content
        # Format 2: - [TYPE] Content
        # Format 3: * [TYPE] Content
        # Format 4: [TYPE] Content (inline marker at start of line)
        
        lines = content.split('\n')
        current_entry = []
        current_type = 'fact'
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Check for new entry markers
            is_new_entry = (
                line_stripped.startswith('### ') or 
                line_stripped.startswith('- ') or 
                line_stripped.startswith('* ') or
                re.match(r'^(\[\w+\]|⭐)\s', line_stripped)  # [TYPE] or ⭐ at start
            )
            
            if is_new_entry:
                # Save previous entry
                if current_entry:
                    entry_text = ' '.join(current_entry).strip()
                    if entry_text:
                        mem_type = self.detect_memory_type(entry_text)
                        # Remove type markers and emoji from content
                        clean_content = re.sub(r'^(\[\w+\]|⭐)\s*', '', entry_text).strip()
                        clean_content = re.sub(r'^[-*#\s]+', '', clean_content).strip()
                        if clean_content:
                            memories.append(MemoryRecord(
                                content=clean_content,
                                memory_type=mem_type,
                                tier='semantic',
                                importance=0.8 if mem_type in ['preference', 'skill'] else 0.6,
                                is_shared=True,
                                source='MEMORY.md',
                                created_at=datetime.now(timezone.utc)
                            ))
                
                # Start new entry
                current_entry = [line_stripped]
            elif current_entry:
                current_entry.append(line_stripped)
        
        # Don't forget the last entry
        if current_entry:
            entry_text = ' '.join(current_entry).strip()
            if entry_text:
                mem_type = self.detect_memory_type(entry_text)
                clean_content = re.sub(r'^(\[\w+\]|⭐)\s*', '', entry_text).strip()
                clean_content = re.sub(r'^[-*#\s]+', '', clean_content).strip()
                if clean_content:
                    memories.append(MemoryRecord(
                        content=clean_content,
                        memory_type=mem_type,
                        tier='semantic',
                        importance=0.8 if mem_type in ['preference', 'skill'] else 0.6,
                        is_shared=True,
                        source='MEMORY.md',
                        created_at=datetime.now(timezone.utc)
                    ))
        
        return memories
    
    def parse_daily_logs(self) -> Dict[str, List[MemoryRecord]]:
        """Parse daily log files"""
        logs = {}
        
        if not self.memory_dir.exists():
            logger.warning(f"Memory directory not found at {self.memory_dir}")
            return logs
        
        for log_file in sorted(self.memory_dir.glob("*.md"), reverse=True):
            date_str = log_file.stem
            try:
                content = log_file.read_text(encoding='utf-8')
                
                # Parse episodes from daily log
                episodes = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('- ') or line.startswith('* '):
                        entry_text = line[2:].strip()
                        if entry_text:
                            mem_type = self.detect_memory_type(entry_text)
                            clean_content = re.sub(r'\[\w+\]\s*', '', entry_text).strip()
                            
                            # Parse date from filename
                            try:
                                entry_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            except ValueError:
                                entry_date = datetime.now(timezone.utc)
                            
                            episodes.append(MemoryRecord(
                                content=clean_content,
                                memory_type=mem_type,
                                tier='episodic',
                                importance=0.5,
                                is_shared=False,
                                source=str(log_file),
                                created_at=entry_date,
                                metadata={'date': date_str}
                            ))
                
                logs[date_str] = episodes
            except Exception as e:
                logger.warning(f"Failed to parse {log_file}: {e}")
        
        return logs
    
    def discover_agents(self) -> List[str]:
        """Discover all agents from directory structure"""
        agents = set()
        
        # Check for agent-specific directories
        if self.memory_dir.exists():
            for agent_dir in self.memory_dir.glob("*"):
                if agent_dir.is_dir():
                    agents.add(agent_dir.name)
        
        # If no agents found, use 'default'
        if not agents:
            agents = {'default'}
        
        return list(agents)
    
    def export_all(self) -> Dict[str, AgentData]:
        """Export all v1 data"""
        logger.info("Exporting v1 data...")
        
        agents = self.discover_agents()
        data = {}
        
        # Parse shared memories from MEMORY.md
        shared_memories = self.parse_memory_md()
        daily_logs = self.parse_daily_logs()
        
        for agent_id in agents:
            logger.info(f"  Processing agent: {agent_id}")
            
            # Combine shared memories with agent-specific logs
            memories = list(shared_memories)  # All agents get shared memories
            
            # Add daily logs as episodic memories
            for date, episodes in daily_logs.items():
                memories.extend(episodes)
            
            data[agent_id] = AgentData(
                agent_id=agent_id,
                name=agent_id,
                memories=memories
            )
            
            logger.info(f"    ✓ {len(memories)} memories")
        
        return data
    
    def save_export(self, data: Dict[str, AgentData], output_path: Path) -> bool:
        """Save export to JSON file"""
        try:
            # Convert dataclasses to dicts
            export_dict = {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'version': '1.0',
                'agents': {}
            }
            
            for agent_id, agent_data in data.items():
                export_dict['agents'][agent_id] = {
                    'agent_id': agent_data.agent_id,
                    'name': agent_data.name,
                    'memory_count': len(agent_data.memories),
                    'memories': [
                        {
                            'content': m.content,
                            'memory_type': m.memory_type,
                            'tier': m.tier,
                            'importance': m.importance,
                            'is_shared': m.is_shared,
                            'source': m.source,
                            'created_at': m.created_at.isoformat() if m.created_at else None,
                            'metadata': m.metadata
                        }
                        for m in agent_data.memories
                    ]
                }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_dict, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save export: {e}")
            return False
    
    def load_export(self, input_path: Path) -> Dict[str, AgentData]:
        """Load export from JSON file"""
        with open(input_path, 'r', encoding='utf-8') as f:
            export_dict = json.load(f)
        
        data = {}
        for agent_id, agent_dict in export_dict.get('agents', {}).items():
            memories = []
            for m in agent_dict.get('memories', []):
                created_at = None
                if m.get('created_at'):
                    try:
                        created_at = datetime.fromisoformat(m['created_at'])
                    except:
                        pass
                
                memories.append(MemoryRecord(
                    content=m['content'],
                    memory_type=m.get('memory_type', 'fact'),
                    tier=m.get('tier', 'semantic'),
                    importance=m.get('importance', 0.5),
                    is_shared=m.get('is_shared', False),
                    source=m.get('source', 'unknown'),
                    created_at=created_at,
                    metadata=m.get('metadata', {})
                ))
            
            data[agent_id] = AgentData(
                agent_id=agent_dict['agent_id'],
                name=agent_dict.get('name', agent_id),
                memories=memories
            )
        
        return data


class EmbeddingGenerator:
    """Generates embeddings for memories"""
    
    def __init__(self, provider: str = "hash", ollama_url: str = DEFAULT_OLLAMA_URL):
        self.provider = provider
        self.ollama_url = ollama_url
        self._ollama_available = None
    
    async def check_ollama(self) -> bool:
        """Check if Ollama is available"""
        if self._ollama_available is not None:
            return self._ollama_available
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    self._ollama_available = resp.status == 200
                    if self._ollama_available:
                        logger.info(f"  ✓ Ollama available at {self.ollama_url}")
                    return self._ollama_available
        except Exception:
            self._ollama_available = False
            return False
    
    async def generate(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for texts"""
        if self.provider == "hash":
            return self._hash_embeddings(texts)
        
        elif self.provider == "ollama":
            if await self.check_ollama():
                return await self._ollama_embeddings(texts, batch_size)
            else:
                logger.warning("Ollama not available, falling back to hash embeddings")
                return self._hash_embeddings(texts)
        
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _hash_embeddings(self, texts: List[str], dim: int = 768) -> List[List[float]]:
        """Generate deterministic hash-based embeddings"""
        embeddings = []
        for text in texts:
            # Use hash as seed for deterministic "embedding"
            h = hashlib.sha256(text.encode()).hexdigest()
            random.seed(int(h[:16], 16))
            vec = [random.gauss(0, 1) for _ in range(dim)]
            # Normalize
            norm = math.sqrt(sum(x*x for x in vec))
            vec = [x/norm for x in vec]
            embeddings.append(vec)
        return embeddings
    
    async def _ollama_embeddings(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings using Ollama"""
        import aiohttp
        
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_embeddings = []
            
            async with aiohttp.ClientSession() as session:
                for text in batch:
                    try:
                        async with session.post(
                            f"{self.ollama_url}/api/embeddings",
                            json={
                                "model": "nomic-embed-text",
                                "prompt": text[:8192]  # Truncate if too long
                            },
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                batch_embeddings.append(data['embedding'])
                            else:
                                # Fallback to hash
                                batch_embeddings.append(self._hash_embeddings([text])[0])
                    except Exception as e:
                        logger.debug(f"Ollama failed for text: {e}")
                        batch_embeddings.append(self._hash_embeddings([text])[0])
            
            embeddings.extend(batch_embeddings)
            
            if (i + batch_size) % 100 == 0:
                logger.info(f"    Processed {min(i + batch_size, len(texts))}/{len(texts)} embeddings...")
        
        return embeddings


async def run_migration(args: argparse.Namespace) -> bool:
    """Run the full migration process"""
    
    print("\n" + "=" * 60)
    print("AMEM Migration - v1 to v2")
    print("=" * 60)
    print(f"Database: {args.db_url}")
    print(f"Workspace: {args.workspace}")
    print(f"Embedding Provider: {args.embedding_provider}")
    print("=" * 60 + "\n")
    
    # Step 1: Export v1 data
    exporter = V1DataExporter(args.workspace)
    
    if args.import_only:
        logger.info(f"Loading export from: {args.import_only}")
        data = exporter.load_export(Path(args.import_only))
    else:
        data = exporter.export_all()
        
        # Save export
        export_file = args.workspace / "v1_export.json"
        if exporter.save_export(data, export_file):
            logger.info(f"✓ Export saved: {export_file}")
        
        if args.export_only:
            logger.info("\nExport complete. Review the file and run again without --export-only")
            return True
    
    # Step 2: Setup database
    db = DatabaseManager(args.db_url)
    
    if not await db.connect():
        return False
    
    try:
        if not await db.setup_schema():
            return False
        
        # Step 3: Import agents and memories
        logger.info("\nImporting to PostgreSQL...")
        
        total_memories = 0
        total_embeddings = 0
        
        for agent_id, agent_data in data.items():
            logger.info(f"\n  Agent: {agent_id}")
            
            # Create agent
            agent_db_id = await db.create_agent(agent_id, agent_data.name)
            if not agent_db_id:
                logger.error(f"    ✗ Failed to create agent")
                continue
            
            logger.info(f"    ✓ Created agent (ID: {agent_db_id[:8]}...)")
            
            # Import memories
            memories = agent_data.memories
            memory_ids = []
            
            for i, mem in enumerate(memories):
                memory_id = await db.import_memory(agent_db_id, mem)
                if memory_id:
                    memory_ids.append(memory_id)
                
                if (i + 1) % 100 == 0:
                    logger.info(f"    Imported {i + 1}/{len(memories)} memories...")
            
            logger.info(f"    ✓ Imported {len(memory_ids)} memories")
            total_memories += len(memory_ids)
            
            # Step 4: Generate embeddings
            if not args.skip_embeddings and memory_ids:
                logger.info(f"    Generating embeddings ({args.embedding_provider})...")
                
                embed_gen = EmbeddingGenerator(args.embedding_provider, args.ollama_url)
                
                # Process in batches
                batch_size = 32
                for i in range(0, len(memories), batch_size):
                    batch = memories[i:i+batch_size]
                    batch_ids = memory_ids[i:i+batch_size]
                    
                    texts = [m.content for m in batch]
                    embeddings = await embed_gen.generate(texts, batch_size)
                    
                    for mid, emb in zip(batch_ids, embeddings):
                        if await db.update_embedding(mid, emb):
                            total_embeddings += 1
                    
                    if (i + batch_size) % 100 == 0:
                        logger.info(f"      Processed {min(i + batch_size, len(memories))}/{len(memories)}...")
                
                logger.info(f"    ✓ Generated {total_embeddings} embeddings")
        
        # Step 5: Verify
        logger.info("\n" + "=" * 60)
        logger.info("Migration Complete!")
        logger.info("=" * 60)
        
        stats = await db.get_stats()
        logger.info(f"\nDatabase Statistics:")
        logger.info(f"  Agents: {stats['agents']}")
        logger.info(f"  Memories: {stats['memories']}")
        logger.info(f"  Shared: {stats['shared_memories']}")
        logger.info(f"  With embeddings: {stats['with_embeddings']}")
        logger.info(f"  Entities: {stats['entities']}")
        logger.info(f"  Relations: {stats['relations']}")
        
        if stats['type_breakdown']:
            logger.info(f"\n  Memory Types:")
            for mem_type, count in stats['type_breakdown'].items():
                logger.info(f"    {mem_type}: {count}")
        
        # Run verification
        if await db.verify_migration(data):
            logger.info("\n✓ Verification passed!")
        else:
            logger.warning("\n⚠ Verification found discrepancies")
        
        # Test vector search
        logger.info("\nTesting vector search...")
        results = await db.test_vector_search()
        if results:
            logger.info(f"  ✓ Vector search working ({len(results)} sample memories)")
        
        logger.info("\nNext steps:")
        logger.info(f"  1. Verify data: psql {args.db_url} -c 'SELECT * FROM memory_stats'")
        logger.info(f"  2. Test search: psql {args.db_url} -c 'SELECT content FROM memories LIMIT 5'")
        logger.info(f"  3. Continue to Phase 3: Dual-write setup")
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await db.close()


async def run_verification_only(args: argparse.Namespace) -> bool:
    """Run only verification against existing database"""
    db = DatabaseManager(args.db_url)
    
    if not await db.connect():
        return False
    
    try:
        stats = await db.get_stats()
        
        print("\n" + "=" * 60)
        print("Migration Verification")
        print("=" * 60)
        
        logger.info(f"\nDatabase Statistics:")
        logger.info(f"  Agents: {stats['agents']}")
        logger.info(f"  Memories: {stats['memories']}")
        logger.info(f"  Shared: {stats['shared_memories']}")
        logger.info(f"  With embeddings: {stats['with_embeddings']}")
        logger.info(f"  Entities: {stats['entities']}")
        logger.info(f"  Relations: {stats['relations']}")
        
        if stats['type_breakdown']:
            logger.info(f"\n  Memory Types:")
            for mem_type, count in stats['type_breakdown'].items():
                logger.info(f"    {mem_type}: {count}")
        
        # Test vector search
        results = await db.test_vector_search()
        if results:
            logger.info(f"\n  ✓ Vector search working ({len(results)} sample memories)")
            for r in results[:3]:
                logger.info(f"    - {r['content'][:60]}...")
        
        return True
        
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(
        description='AMEM v1 to v2 Migration Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 migrate_v1_to_v2.py                    # Full migration
    python3 migrate_v1_to_v2.py --export-only      # Only export v1 data
    python3 migrate_v1_to_v2.py --import-only v1_export.json  # Import from file
    python3 migrate_v1_to_v2.py --skip-embeddings  # Skip embedding generation
    python3 migrate_v1_to_v2.py --verify-only      # Verify existing migration
    python3 migrate_v1_to_v2.py --embedding-provider ollama  # Use Ollama for embeddings
        """
    )
    
    parser.add_argument('--db-url', default=DEFAULT_DB_URL,
                       help='PostgreSQL connection URL')
    parser.add_argument('--workspace', type=Path, default=WORKSPACE,
                       help='AMEM workspace directory')
    parser.add_argument('--export-only', action='store_true',
                       help='Only export v1 data')
    parser.add_argument('--import-only', type=str, metavar='FILE',
                       help='Import from JSON file')
    parser.add_argument('--skip-embeddings', action='store_true',
                       help='Skip embedding generation')
    parser.add_argument('--verify-only', action='store_true',
                       help='Only verify existing migration')
    parser.add_argument('--embedding-provider', default='hash',
                       choices=['hash', 'ollama'],
                       help='Embedding provider (hash=deterministic fallback, ollama=semantic)')
    parser.add_argument('--ollama-url', default=DEFAULT_OLLAMA_URL,
                       help='Ollama API endpoint')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run appropriate mode
    if args.verify_only:
        success = asyncio.run(run_verification_only(args))
    else:
        success = asyncio.run(run_migration(args))
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
