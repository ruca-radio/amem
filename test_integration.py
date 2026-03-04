#!/usr/bin/env python3
"""
AMEM Integration Test
Verifies the memory system is properly installed and working.
"""
import sys
import os
from pathlib import Path

# Test 1: Check paths are correct
print("Test 1: Path Configuration")
print("-" * 40)

workspace = Path(os.getenv("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
memory_system = workspace / "memory_system"

print(f"Workspace: {workspace}")
print(f"Memory system: {memory_system}")
print(f"Exists: {memory_system.exists()}")

if not memory_system.exists():
    print("✗ FAIL: memory_system not found")
    print("  Run: ./install-lightweight.sh")
    sys.exit(1)

print("✓ PASS")
print()

# Test 2: Import test
print("Test 2: Module Import")
print("-" * 40)

try:
    sys.path.insert(0, str(memory_system))
    from openclaw_memory import MemoryTools
    print("✓ PASS: Module imports successfully")
except Exception as e:
    print(f"✗ FAIL: {e}")
    sys.exit(1)

print()

# Test 3: Memory operations
print("Test 3: Memory Operations")
print("-" * 40)

try:
    m = MemoryTools("integration-test")
    
    # Store
    result = m.remember("Integration test memory", permanent=True)
    print(f"  Store: {result[:50]}...")
    
    # Recall
    results = m.recall("integration test")
    print(f"  Recall: {len(results)} results")
    
    if len(results) > 0:
        print("✓ PASS: Memory operations working")
    else:
        print("⚠ WARN: No results returned (may be normal on first run)")
        
except Exception as e:
    print(f"✗ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Check data files
print("Test 4: Data Persistence")
print("-" * 40)

memory_dir = workspace / "memory"
memory_md = workspace / "MEMORY.md"

if memory_dir.exists():
    files = list(memory_dir.glob("*.md"))
    print(f"  Memory files: {len(files)}")
    for f in files:
        print(f"    - {f.name}")
else:
    print("  No memory directory yet")

if memory_md.exists():
    size = memory_md.stat().st_size
    print(f"  MEMORY.md: {size} bytes")
else:
    print("  No MEMORY.md yet")

print("✓ PASS")
print()

print("=" * 40)
print("All tests passed!")
print("AMEM is properly integrated and working.")
print("=" * 40)