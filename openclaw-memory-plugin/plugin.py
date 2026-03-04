#!/usr/bin/env python3
"""
OpenClaw Memory Plugin - Direct Tool Integration
Registers memory tools directly with OpenClaw's tool system.
No CLI required - agents call tools directly.
"""
import json
import sys
from pathlib import Path

# Add native to path
NATIVE_DIR = Path(__file__).parent.parent / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools
from auto_extract import AutoMemoryExtractor
from graph_memory import MemoryGraphTools


class OpenClawMemoryPlugin:
    """
    OpenClaw Plugin Interface
    
    This class provides the tools that OpenClaw agents can call directly.
    No CLI wrapper needed - agents use the tool system.
    """
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.memory = MemoryTools(agent_id)
        self.extractor = AutoMemoryExtractor(agent_id)
        self.graph = MemoryGraphTools(agent_id)
    
    def memory_search(self, query: str, k: int = 5) -> str:
        """
        Search agent memory for relevant information.
        
        Args:
            query: Search query (e.g., "user preferences", "tech stack")
            k: Number of results to return (default: 5)
        
        Returns:
            JSON string of search results
        """
        results = self.memory.recall(query, k=k)
        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results)
        }, indent=2)
    
    def memory_store(self, content: str, permanent: bool = False, 
                     memory_type: str = "fact") -> str:
        """
        Store information in agent memory.
        
        Args:
            content: Content to remember
            permanent: If True, stores in long-term semantic memory
            memory_type: Type of memory (fact, preference, episode, skill)
        
        Returns:
            Confirmation message
        """
        result = self.memory.remember(
            content=content,
            memory_type=memory_type,
            permanent=permanent
        )
        
        # Also extract entities for graph
        self.graph.remember(content, extract_entities=True, permanent=permanent)
        
        return json.dumps({
            "stored": True,
            "content": content[:100],
            "permanent": permanent,
            "type": memory_type
        })
    
    def memory_get(self, path: str, from_line: int = None, 
                   lines: int = None) -> str:
        """
        Read specific memory file content.
        
        Args:
            path: File path (e.g., "MEMORY.md" or "memory/2026-03-04.md")
            from_line: Starting line number (1-indexed)
            lines: Number of lines to read
        
        Returns:
            File content
        """
        content = self.memory.store.get(path, from_line, lines)
        return json.dumps({
            "path": path,
            "content": content
        })
    
    def memory_graph_query(self, entity: str) -> str:
        """
        Query entity relationships in memory graph.
        
        Args:
            entity: Entity name (e.g., "Python", "Docker", "user")
        
        Returns:
            JSON string of related entities and relationships
        """
        results = self.graph.graph.query(entity)
        return json.dumps({
            "entity": entity,
            "relationships": results,
            "count": len(results)
        }, indent=2)
    
    def memory_ask(self, question: str) -> str:
        """
        Ask a question using memory graph and semantic search.
        
        Args:
            question: Natural language question
        
        Returns:
            Answer based on memory
        """
        answer = self.graph.ask(question)
        return json.dumps({
            "question": question,
            "answer": answer
        })
    
    def memory_stats(self) -> str:
        """
        Get memory system statistics.
        
        Returns:
            JSON string of memory stats
        """
        stats = self.memory.store.stats()
        return json.dumps(stats, indent=2)
    
    def memory_context(self, query: str, max_tokens: int = 1500) -> str:
        """
        Get formatted memory context for prompt injection.
        
        Args:
            query: Context query (e.g., "current task", "user preferences")
            max_tokens: Maximum tokens for context
        
        Returns:
            Formatted context string
        """
        context = self.memory.context_for_prompt(query, max_tokens)
        return json.dumps({
            "query": query,
            "context": context
        })


# Global plugin instance
_plugin = None

def get_plugin(agent_id: str = "default"):
    """Get or create plugin instance"""
    global _plugin
    if _plugin is None:
        _plugin = OpenClawMemoryPlugin(agent_id)
    return _plugin


# Tool functions that OpenClaw calls directly
def memory_search(query: str, k: int = 5) -> str:
    """Tool: Search agent memory"""
    return get_plugin().memory_search(query, k)

def memory_store(content: str, permanent: bool = False, 
                 memory_type: str = "fact") -> str:
    """Tool: Store information in memory"""
    return get_plugin().memory_store(content, permanent, memory_type)

def memory_get(path: str, from_line: int = None, lines: int = None) -> str:
    """Tool: Read memory file"""
    return get_plugin().memory_get(path, from_line, lines)

def memory_graph_query(entity: str) -> str:
    """Tool: Query memory graph"""
    return get_plugin().memory_graph_query(entity)

def memory_ask(question: str) -> str:
    """Tool: Ask question using memory"""
    return get_plugin().memory_ask(question)

def memory_stats() -> str:
    """Tool: Get memory stats"""
    return get_plugin().memory_stats()

def memory_context(query: str, max_tokens: int = 1500) -> str:
    """Tool: Get memory context for prompts"""
    return get_plugin().memory_context(query, max_tokens)


# For testing
if __name__ == "__main__":
    print("OpenClaw Memory Plugin - Direct Tool Integration")
    print("=" * 60)
    
    plugin = OpenClawMemoryPlugin("test")
    
    # Test store
    print("\n1. Storing memory...")
    result = plugin.memory_store("User prefers Python for automation", permanent=True)
    print(result)
    
    # Test search
    print("\n2. Searching...")
    result = plugin.memory_search("Python")
    print(result)
    
    # Test stats
    print("\n3. Stats...")
    result = plugin.memory_stats()
    print(result)