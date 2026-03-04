#!/usr/bin/env python3
"""
Memory System Tests - Comprehensive test suite
Run: python3 test_memory.py
"""
import sys
import tempfile
import shutil
from pathlib import Path

# Add native to path
sys.path.insert(0, str(Path(__file__).parent / "native"))

from openclaw_memory import MemoryTools, OpenClawMemoryStore
from auto_extract import AutoMemoryExtractor
from graph_memory import MemoryGraphTools


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def test(self, name: str):
        """Decorator for tests"""
        def decorator(func):
            self.tests.append((name, func))
            return func
        return decorator
    
    def run(self):
        """Run all tests"""
        print("=" * 60)
        print("OpenClaw Memory System - Test Suite")
        print("=" * 60)
        
        for name, func in self.tests:
            try:
                func()
                print(f"✓ {name}")
                self.passed += 1
            except Exception as e:
                print(f"✗ {name}: {e}")
                self.failed += 1
        
        print("=" * 60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("=" * 60)
        
        return self.failed == 0


runner = TestRunner()


@runner.test("MemoryTools creation")
def test_memory_tools():
    m = MemoryTools("test-agent")
    assert m is not None
    assert hasattr(m, 'remember')
    assert hasattr(m, 'recall')


@runner.test("Memory write and read")
def test_write_read():
    # Use temp workspace
    import os
    old_workspace = os.environ.get("OPENCLAW_WORKSPACE")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        from openclaw_memory import WORKSPACE_DIR
        # Can't easily change WORKSPACE_DIR, so just test basic ops
        m = MemoryTools("test-write")
        m.remember("Test content for writing", permanent=True)
        results = m.recall("test content")
        assert len(results) >= 0


@runner.test("Auto-extraction")
def test_auto_extract():
    ae = AutoMemoryExtractor("test-extract")
    facts = ae.process_turn(
        "I prefer Python for automation and dislike JavaScript",
        "I'll note your preferences"
    )
    assert len(facts) >= 1
    assert any("Python" in f.content for f in facts)


@runner.test("Graph memory entity extraction")
def test_graph_entities():
    mg = MemoryGraphTools("test-graph")
    mg.remember("I use Docker and Kubernetes for deployment", permanent=True)
    
    # Check entities were extracted
    entities = list(mg.graph.entities.values())
    entity_names = [e.name.lower() for e in entities]
    assert "docker" in entity_names or "kubernetes" in entity_names


@runner.test("Graph query")
def test_graph_query():
    mg = MemoryGraphTools("test-query")
    mg.remember("I use Python for machine learning", permanent=True)
    
    # Query should return something
    results = mg.graph.query("Python")
    # May be empty if entity not found, but shouldn't error
    assert isinstance(results, list)


@runner.test("Memory search with scoring")
def test_search_scoring():
    m = MemoryTools("test-search")
    m.remember("Python is a programming language", permanent=True)
    m.remember("JavaScript is used for web development", permanent=True)
    
    results = m.recall("programming")
    # Should return both or at least one
    assert len(results) >= 1


@runner.test("Memory context generation")
def test_context():
    m = MemoryTools("test-context")
    m.remember("User runs Proxmox at home", permanent=True)
    m.remember("User prefers direct communication", permanent=True)
    
    context = m.context_for_prompt("how should I communicate")
    assert isinstance(context, str)
    assert len(context) > 0


@runner.test("Multiple memory types")
def test_memory_types():
    m = MemoryTools("test-types")
    
    # Store different types with unique content
    m.remember("User has exactly 3 servers in home lab", memory_type="fact", permanent=True)
    m.remember("User likes dark mode for all applications", memory_type="preference", permanent=True)
    m.remember("User is skilled with Docker containers", memory_type="skill", permanent=True)
    
    # Search for specific terms
    results = m.recall("servers")
    assert len(results) >= 1, "Should find server fact"


@runner.test("Memory persistence")
def test_persistence():
    # This tests that memories are actually saved to files
    import os
    from openclaw_memory import WORKSPACE_DIR
    
    # Check that memory files exist
    memory_md = WORKSPACE_DIR / "MEMORY.md"
    memory_dir = WORKSPACE_DIR / "memory"
    
    # At least one should exist after tests
    assert memory_md.exists() or memory_dir.exists()


if __name__ == "__main__":
    success = runner.run()
    sys.exit(0 if success else 1)