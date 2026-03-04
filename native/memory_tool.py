#!/usr/bin/env python3
"""
OpenClaw Memory Tool
Integrates with OpenClaw's tool system for automatic memory management.
Add this to your agent's available tools.
"""
import sys
sys.path.insert(0, "/root/.openclaw/workspace/memory-system/native")

from memory import OpenClawMemory, MemoryType, MemoryTier
from typing import List, Optional
import json

# Global memory instance (per-agent)
_memory_instances = {}

def get_memory(agent_id: str = "default") -> OpenClawMemory:
    """Get or create memory instance for agent"""
    if agent_id not in _memory_instances:
        _memory_instances[agent_id] = OpenClawMemory(agent_id)
    return _memory_instances[agent_id]


# Tool functions for OpenClaw integration
def memory_remember(content: str, memory_type: str = "fact", importance: float = 0.5, 
                    permanent: bool = False, tags: List[str] = None, agent_id: str = "default") -> str:
    """
    Store a memory for future retrieval.
    
    Args:
        content: The information to remember
        memory_type: fact, preference, episode, or skill
        importance: 0.0-1.0, how important this memory is
        permanent: If True, stores in semantic tier (long-term)
        tags: Optional list of tags for organization
        agent_id: Which agent this memory belongs to
    
    Returns:
        Memory ID string
    """
    mem = get_memory(agent_id)
    mid = mem.remember(content, memory_type, importance, permanent, tags or [])
    return f"Stored memory {mid}: {content[:50]}..."


def memory_recall(query: str, k: int = 5, agent_id: str = "default") -> str:
    """
    Retrieve relevant memories based on query.
    
    Args:
        query: What to search for
        k: Number of memories to return
        agent_id: Which agent's memories to search
    
    Returns:
        JSON string of memory contents
    """
    mem = get_memory(agent_id)
    results = mem.recall(query, k)
    return json.dumps(results, indent=2)


def memory_context(query: str, max_tokens: int = 1000, agent_id: str = "default") -> str:
    """
    Get formatted memory context for LLM prompt injection.
    
    Args:
        query: Context query (e.g., "user preferences", "current task")
        max_tokens: Approximate token budget for context
        agent_id: Which agent's memories to use
    
    Returns:
        Formatted context string ready for prompt insertion
    """
    mem = get_memory(agent_id)
    return mem.context_for_prompt(query, max_tokens)


def memory_stats(agent_id: str = "default") -> str:
    """Get memory statistics for agent"""
    mem = get_memory(agent_id)
    return json.dumps(mem.store.stats(), indent=2)


# Auto-memory wrapper for conversations
class AutoMemory:
    """
    Wraps an agent's response to automatically extract and store memories.
    Use this to make any agent memory-enabled without code changes.
    """
    
    def __init__(self, agent_id: str, extract_facts: bool = True, 
                 extract_preferences: bool = True):
        self.agent_id = agent_id
        self.mem = get_memory(agent_id)
        self.extract_facts = extract_facts
        self.extract_preferences = extract_preferences
        self.session_memories = []
    
    def on_user_message(self, message: str) -> str:
        """Process user message - stores as episode"""
        # Store the interaction
        self.mem.remember(
            f"User said: {message[:200]}",
            memory_type="episode",
            importance=0.4,
            permanent=False
        )
        return message
    
    def on_agent_response(self, response: str, context: str = "") -> str:
        """Process agent response - can extract facts/preferences"""
        # Store agent's response as episode
        self.mem.remember(
            f"Agent responded: {response[:200]}",
            memory_type="episode", 
            importance=0.3,
            permanent=False
        )
        return response
    
    def get_context(self, query: str = "current conversation") -> str:
        """Get memory-augmented context for next turn"""
        return self.mem.context_for_prompt(query, max_tokens=1500)


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw Memory Tool")
    parser.add_argument("command", choices=["remember", "recall", "context", "stats"])
    parser.add_argument("--agent", default="default", help="Agent ID")
    parser.add_argument("--content", help="Content to remember")
    parser.add_argument("--query", help="Query for recall/context")
    parser.add_argument("--type", default="fact", choices=["fact", "preference", "episode", "skill"])
    parser.add_argument("--importance", type=float, default=0.5)
    parser.add_argument("--permanent", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    
    args = parser.parse_args()
    
    if args.command == "remember":
        if not args.content:
            print("Error: --content required")
            sys.exit(1)
        print(memory_remember(args.content, args.type, args.importance, args.permanent, agent_id=args.agent))
    
    elif args.command == "recall":
        if not args.query:
            print("Error: --query required")
            sys.exit(1)
        print(memory_recall(args.query, args.k, args.agent))
    
    elif args.command == "context":
        if not args.query:
            print("Error: --query required")
            sys.exit(1)
        print(memory_context(args.query, agent_id=args.agent))
    
    elif args.command == "stats":
        print(memory_stats(args.agent))