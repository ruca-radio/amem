"""
Memory Compactor - Background service for tier management
Handles promotion/demotion, compression, and decay
"""
import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Optional

import asyncpg
import httpx

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://memory:memory@postgres:5432/memory")
MEMORY_API_URL = os.getenv("MEMORY_API_URL", "http://memory-api:8000")
EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8001")


class MemoryCompactor:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    
    async def close(self):
        if self.pool:
            await self.pool.close()
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMBEDDING_URL}/embed",
                json={"text": text},
                timeout=30.0
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
    
    async def promote_memories(self):
        """
        Promote memories from episodic -> semantic based on:
        - High importance score
        - Frequent access
        - Age (older = more likely to be core knowledge)
        """
        async with self.pool.acquire() as conn:
            # Find candidates for promotion
            rows = await conn.fetch(
                """
                SELECT id, content, agent_id, access_count, importance_score, created_at
                FROM memories
                WHERE tier = 'episodic'
                  AND superseded_by IS NULL
                  AND importance_score >= 0.7
                  AND access_count >= 3
                  AND created_at < NOW() - INTERVAL '7 days'
                ORDER BY importance_score * access_count DESC
                LIMIT 100
                """
            )
            
            promoted = 0
            for row in rows:
                # Mark old as superseded
                await conn.execute(
                    "UPDATE memories SET superseded_by = $1 WHERE id = $1",
                    row["id"]
                )
                
                # Create new semantic memory
                embedding = await self.get_embedding(row["content"])
                await conn.execute(
                    """
                    INSERT INTO memories 
                        (content, embedding, agent_id, memory_type, tier, 
                         importance_score, source, tags)
                    VALUES ($1, $2, $3, 'fact', 'semantic', $4, 'promoted', 
                            ARRAY['auto-promoted'])
                    """,
                    row["content"], embedding, row["agent_id"],
                    min(row["importance_score"] * 1.1, 1.0)  # Boost importance
                )
                promoted += 1
            
            return promoted
    
    async def compress_episodes(self):
        """
        Compress old episodic memories into summaries
        Group by agent and time window, create condensed version
        """
        async with self.pool.acquire() as conn:
            # Find old episodic memories to compress
            rows = await conn.fetch(
                """
                SELECT id, content, agent_id, session_id, created_at
                FROM memories
                WHERE tier = 'episodic'
                  AND superseded_by IS NULL
                  AND compression_level = 0
                  AND created_at < NOW() - INTERVAL '3 days'
                ORDER BY agent_id, session_id, created_at
                LIMIT 500
                """
            )
            
            if len(rows) < 5:
                return 0  # Not enough to compress
            
            # Group by agent/session
            groups = {}
            for row in rows:
                key = (row["agent_id"], row["session_id"] or "none")
                if key not in groups:
                    groups[key] = []
                groups[key].append(row)
            
            compressed = 0
            for (agent_id, session_id), memories in groups.items():
                if len(memories) < 3:
                    continue
                
                # Simple compression: concatenate and summarize
                # In production, this would call an LLM for proper summarization
                contents = [m["content"] for m in memories]
                summary = f"Session summary ({len(memories)} events): " + " | ".join(
                    c[:100] for c in contents[:5]
                )
                
                # Mark originals as superseded
                ids = [m["id"] for m in memories]
                await conn.execute(
                    "UPDATE memories SET superseded_by = $1 WHERE id = ANY($2)",
                    memories[0]["id"], ids
                )
                
                # Create compressed memory
                embedding = await self.get_embedding(summary)
                await conn.execute(
                    """
                    INSERT INTO memories 
                        (content, embedding, agent_id, session_id, memory_type, tier,
                         source, compression_level, original_ids)
                    VALUES ($1, $2, $3, $4, 'episode', 'episodic', 'compressed', 1, $5)
                    """,
                    summary, embedding, agent_id, 
                    session_id if session_id != "none" else None,
                    ids
                )
                compressed += len(memories)
            
            return compressed
    
    async def apply_decay(self):
        """
        Apply time-based decay to episodic memories
        Reduce importance, eventually mark for archival
        """
        async with self.pool.acquire() as conn:
            # Decay old episodic memories
            result = await conn.execute(
                """
                UPDATE memories
                SET importance_score = importance_score * 0.95,
                    decay_factor = decay_factor * 0.98
                WHERE tier = 'episodic'
                  AND superseded_by IS NULL
                  AND last_accessed < NOW() - INTERVAL '1 day'
                """
            )
            
            # Mark heavily decayed memories as superseded
            archived = await conn.fetchval(
                """
                UPDATE memories
                SET superseded_by = id
                WHERE tier = 'episodic'
                  AND superseded_by IS NULL
                  AND importance_score < 0.1
                  AND decay_factor < 0.5
                  AND last_accessed < NOW() - INTERVAL '30 days'
                RETURNING COUNT(*)
                """
            )
            
            return {"decayed": result, "archived": archived or 0}
    
    async def cleanup_working_memory(self):
        """Remove stale working memory snapshots"""
        async with self.pool.acquire() as conn:
            deleted = await conn.fetchval(
                """
                DELETE FROM working_memory
                WHERE updated_at < NOW() - INTERVAL '24 hours'
                RETURNING COUNT(*)
                """
            )
            return deleted or 0
    
    async def run_cycle(self):
        """Run one compaction cycle"""
        print(f"[{datetime.now()}] Starting compaction cycle...")
        
        promoted = await self.promote_memories()
        print(f"  Promoted {promoted} memories to semantic tier")
        
        compressed = await self.compress_episodes()
        print(f"  Compressed {compressed} episodic memories")
        
        decay_stats = await self.apply_decay()
        print(f"  Applied decay: {decay_stats}")
        
        cleaned = await self.cleanup_working_memory()
        print(f"  Cleaned {cleaned} stale working memory snapshots")
        
        print(f"[{datetime.now()}] Compaction complete")
    
    async def run_daemon(self, interval_minutes: int = 60):
        """Run as continuous daemon"""
        await self.connect()
        try:
            while True:
                await self.run_cycle()
                await asyncio.sleep(interval_minutes * 60)
        finally:
            await self.close()


async def main():
    import sys
    
    compactor = MemoryCompactor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        await compactor.run_daemon()
    else:
        # Single run
        await compactor.connect()
        try:
            await compactor.run_cycle()
        finally:
            await compactor.close()


if __name__ == "__main__":
    asyncio.run(main())