#!/usr/bin/env python3
"""
Verify AMEM v2 database migration

Usage:
    python3 verify_migration.py                    # Full verification
    python3 verify_migration.py --quick            # Quick check
    python3 verify_migration.py --db-url URL       # Custom database URL
"""

import asyncio
import asyncpg
import argparse
import sys
from typing import Dict, Any

DEFAULT_DB_URL = "postgresql://amem:amem@localhost/amem"


async def check_connection(db_url: str) -> bool:
    """Check database connection"""
    try:
        conn = await asyncpg.connect(db_url)
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        print(f"✓ Connected to PostgreSQL")
        print(f"  Version: {version[:50]}...")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


async def check_extensions(conn: asyncpg.Connection) -> bool:
    """Check required extensions"""
    print("\n[Extensions]")
    
    extensions = await conn.fetch(
        "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'uuid-ossp')"
    )
    
    found = {row['extname']: row['extversion'] for row in extensions}
    
    checks = [
        ('vector', 'pgvector for embeddings'),
        ('uuid-ossp', 'UUID generation'),
    ]
    
    all_ok = True
    for ext, description in checks:
        if ext in found:
            print(f"  ✓ {ext} ({found[ext]}) - {description}")
        else:
            print(f"  ✗ {ext} - {description}")
            all_ok = False
    
    return all_ok


async def check_tables(conn: asyncpg.Connection) -> bool:
    """Check required tables"""
    print("\n[Tables]")
    
    tables = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    
    found = {row['tablename'] for row in tables}
    
    required = [
        ('agents', 'Agent registry'),
        ('memories', 'Memory storage with vectors'),
        ('entities', 'Knowledge graph nodes'),
        ('relations', 'Knowledge graph edges'),
        ('audit_log', 'Audit trail'),
    ]
    
    all_ok = True
    for table, description in required:
        if table in found:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"  ✓ {table} ({count} rows) - {description}")
        else:
            print(f"  ✗ {table} - {description}")
            all_ok = False
    
    return all_ok


async def check_indexes(conn: asyncpg.Connection) -> bool:
    """Check required indexes"""
    print("\n[Indexes]")
    
    indexes = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    )
    
    found = {row['indexname'] for row in indexes}
    
    required = [
        ('idx_memories_agent', 'Agent lookup'),
        ('idx_memories_embedding_ivf', 'Vector search (IVFFlat)'),
    ]
    
    all_ok = True
    for idx, description in required:
        if idx in found:
            print(f"  ✓ {idx} - {description}")
        else:
            print(f"  ✗ {idx} - {description}")
            all_ok = False
    
    return all_ok


async def check_vector_search(conn: asyncpg.Connection) -> bool:
    """Test vector search functionality"""
    print("\n[Vector Search]")
    
    # Check if we have memories with embeddings
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
    )
    
    if count == 0:
        print("  ⚠ No memories with embeddings found")
        print("    Run migration to generate embeddings")
        return True  # Not a failure, just no data yet
    
    print(f"  ✓ {count} memories with embeddings")
    
    # Test vector similarity query
    try:
        # Create a test vector
        test_vector = [0.1] * 768
        
        result = await conn.fetch(
            """
            SELECT id, content, embedding <=> $1::vector AS distance
            FROM memories
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT 1
            """,
            test_vector
        )
        
        if result:
            print(f"  ✓ Vector similarity query working")
            print(f"    Sample: {result[0]['content'][:50]}...")
            return True
    except Exception as e:
        print(f"  ✗ Vector query failed: {e}")
        return False
    
    return True


async def check_stats(conn: asyncpg.Connection) -> Dict[str, Any]:
    """Get migration statistics"""
    print("\n[Statistics]")
    
    stats = {}
    
    # Basic counts
    stats['agents'] = await conn.fetchval("SELECT COUNT(*) FROM agents")
    stats['memories'] = await conn.fetchval("SELECT COUNT(*) FROM memories")
    stats['entities'] = await conn.fetchval("SELECT COUNT(*) FROM entities")
    stats['relations'] = await conn.fetchval("SELECT COUNT(*) FROM relations")
    
    # Memory breakdown
    type_counts = await conn.fetch(
        "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
    )
    
    # Embedding coverage
    with_embeddings = await conn.fetchval(
        "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
    )
    
    print(f"  Agents: {stats['agents']}")
    print(f"  Memories: {stats['memories']}")
    for row in type_counts:
        print(f"    - {row['memory_type']}: {row['count']}")
    print(f"  With embeddings: {with_embeddings} ({with_embeddings/stats['memories']*100:.1f}%)")
    print(f"  Entities: {stats['entities']}")
    print(f"  Relations: {stats['relations']}")
    
    return stats


async def run_verification(db_url: str, quick: bool = False) -> bool:
    """Run full verification"""
    print("=" * 60)
    print("AMEM v2 Migration Verification")
    print("=" * 60)
    print(f"Database: {db_url}")
    print("=" * 60)
    
    # Check connection
    if not await check_connection(db_url):
        return False
    
    conn = await asyncpg.connect(db_url)
    
    try:
        checks = []
        
        # Run checks
        checks.append(("Extensions", await check_extensions(conn)))
        checks.append(("Tables", await check_tables(conn)))
        
        if not quick:
            checks.append(("Indexes", await check_indexes(conn)))
            checks.append(("Vector Search", await check_vector_search(conn)))
            await check_stats(conn)
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        
        for name, passed in checks:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {name}")
        
        all_passed = all(passed for _, passed in checks)
        
        if all_passed:
            print("\n  🎉 All checks passed!")
        else:
            print("\n  ⚠ Some checks failed")
        
        return all_passed
        
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description='Verify AMEM v2 migration')
    parser.add_argument('--db-url', default=DEFAULT_DB_URL, help='Database URL')
    parser.add_argument('--quick', action='store_true', help='Quick check only')
    args = parser.parse_args()
    
    success = asyncio.run(run_verification(args.db_url, args.quick))
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
