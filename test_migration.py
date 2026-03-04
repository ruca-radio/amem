#!/usr/bin/env python3
"""
Test script for AMEM v1 to v2 migration

This script tests the migration logic without requiring a running PostgreSQL database.
It validates:
1. Data export from v1 format
2. Data transformation
3. Schema validation
4. Embedding generation

Usage:
    python3 test_migration.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from migrate_v1_to_v2 import V1DataExporter, MemoryRecord, AgentData, EmbeddingGenerator


def test_memory_type_detection():
    """Test memory type detection"""
    print("\n[Test] Memory Type Detection")
    print("-" * 40)
    
    exporter = V1DataExporter(Path("/tmp"))
    
    test_cases = [
        ("[FACT] User runs Proxmox", "fact"),
        ("[PREFERENCE] User likes dark mode", "preference"),
        ("[PREF] User likes dark mode", "preference"),
        ("⭐ User likes dark mode", "preference"),
        ("[SKILL] User knows Docker", "skill"),
        ("[EPISODE] Debugged network issue", "episode"),
        ("Just a regular fact", "fact"),
    ]
    
    passed = 0
    for content, expected in test_cases:
        result = exporter.detect_memory_type(content)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        print(f"  {status} '{content[:40]}...' -> {result}")
    
    print(f"\n  Passed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_export():
    """Test data export from v1"""
    print("\n[Test] Data Export")
    print("-" * 40)
    
    workspace = Path("/root/.openclaw/workspace")
    exporter = V1DataExporter(workspace)
    
    data = exporter.export_all()
    
    print(f"  Agents found: {len(data)}")
    
    total_memories = 0
    for agent_id, agent_data in data.items():
        print(f"\n  Agent: {agent_id}")
        print(f"    Memories: {len(agent_data.memories)}")
        total_memories += len(agent_data.memories)
        
        # Show type breakdown
        type_counts = {}
        for mem in agent_data.memories:
            type_counts[mem.memory_type] = type_counts.get(mem.memory_type, 0) + 1
        
        for mem_type, count in type_counts.items():
            print(f"      {mem_type}: {count}")
    
    print(f"\n  Total memories: {total_memories}")
    
    # Save export for inspection
    export_file = Path("/tmp/test_v1_export.json")
    exporter.save_export(data, export_file)
    print(f"  Export saved: {export_file}")
    
    return total_memories > 0


def test_embedding_generation():
    """Test embedding generation"""
    print("\n[Test] Embedding Generation")
    print("-" * 40)
    
    texts = [
        "User runs Proxmox at home lab",
        "User prefers Python for automation",
        "Docker is used for containers"
    ]
    
    # Test hash-based embeddings
    print("  Testing hash-based embeddings...")
    embed_gen = EmbeddingGenerator("hash")
    embeddings = embed_gen._hash_embeddings(texts)
    
    print(f"    Generated {len(embeddings)} embeddings")
    print(f"    Dimension: {len(embeddings[0])}")
    
    # Verify deterministic
    embeddings2 = embed_gen._hash_embeddings(texts)
    deterministic = all(
        e1 == e2 for e1, e2 in zip(embeddings, embeddings2)
    )
    print(f"    Deterministic: {'✓' if deterministic else '✗'}")
    
    # Verify normalized
    import math
    norms = [math.sqrt(sum(x*x for x in emb)) for emb in embeddings]
    normalized = all(abs(n - 1.0) < 0.001 for n in norms)
    print(f"    Normalized: {'✓' if normalized else '✗'}")
    
    return len(embeddings) == len(texts) and deterministic


def test_schema_validation():
    """Test SQL schema validity (basic checks)"""
    print("\n[Test] Schema Validation")
    print("-" * 40)
    
    schema_file = Path(__file__).parent / "migrations" / "001_initial_schema.sql"
    
    if not schema_file.exists():
        print(f"  ✗ Schema file not found: {schema_file}")
        return False
    
    schema = schema_file.read_text()
    
    # Check for required tables
    required_tables = [
        "agents", "memories", "entities", "relations", "audit_log"
    ]
    
    print("  Checking required tables:")
    all_found = True
    for table in required_tables:
        found = f"CREATE TABLE IF NOT EXISTS {table}" in schema
        status = "✓" if found else "✗"
        if not found:
            all_found = False
        print(f"    {status} {table}")
    
    # Check for pgvector
    print("\n  Checking pgvector:")
    has_vector = "CREATE EXTENSION IF NOT EXISTS vector" in schema
    has_vector_col = "VECTOR(768)" in schema
    print(f"    {'✓' if has_vector else '✗'} Extension creation")
    print(f"    {'✓' if has_vector_col else '✗'} Vector column type")
    
    # Check for indexes
    print("\n  Checking indexes:")
    has_embedding_idx = "idx_memories_embedding" in schema
    print(f"    {'✓' if has_embedding_idx else '✗'} Embedding index")
    
    return all_found and has_vector and has_vector_col


def test_data_transformation():
    """Test data transformation from v1 to v2 format"""
    print("\n[Test] Data Transformation")
    print("-" * 40)
    
    workspace = Path("/root/.openclaw/workspace")
    exporter = V1DataExporter(workspace)
    
    # Parse memories
    memories = exporter.parse_memory_md()
    
    print(f"  Parsed {len(memories)} memories from MEMORY.md")
    
    # Check for required fields
    required_fields = ['content', 'memory_type', 'importance', 'is_shared']
    
    all_valid = True
    for i, mem in enumerate(memories[:5]):  # Check first 5
        print(f"\n  Memory {i+1}:")
        print(f"    Content: {mem.content[:50]}...")
        print(f"    Type: {mem.memory_type}")
        print(f"    Importance: {mem.importance}")
        print(f"    Shared: {mem.is_shared}")
        
        # Validate fields
        for field in required_fields:
            if not hasattr(mem, field) or getattr(mem, field) is None:
                print(f"    ✗ Missing field: {field}")
                all_valid = False
    
    return all_valid and len(memories) > 0


def test_json_serialization():
    """Test JSON serialization of export data"""
    print("\n[Test] JSON Serialization")
    print("-" * 40)
    
    workspace = Path("/root/.openclaw/workspace")
    exporter = V1DataExporter(workspace)
    
    data = exporter.export_all()
    
    # Serialize to JSON
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
    
    # Test serialization
    try:
        json_str = json.dumps(export_dict, indent=2)
        print(f"  ✓ JSON serialization successful")
        print(f"    Size: {len(json_str)} bytes")
        
        # Test deserialization
        loaded = json.loads(json_str)
        print(f"  ✓ JSON deserialization successful")
        print(f"    Agents: {len(loaded['agents'])}")
        
        return True
    except Exception as e:
        print(f"  ✗ JSON error: {e}")
        return False


def main():
    print("=" * 60)
    print("AMEM Migration Test Suite")
    print("=" * 60)
    
    tests = [
        ("Schema Validation", test_schema_validation),
        ("Memory Type Detection", test_memory_type_detection),
        ("Data Export", test_export),
        ("Data Transformation", test_data_transformation),
        ("JSON Serialization", test_json_serialization),
        ("Embedding Generation", test_embedding_generation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n  ✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n  🎉 All tests passed!")
        return 0
    else:
        print("\n  ⚠ Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
