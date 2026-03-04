#!/usr/bin/env python3
"""
AMEM Client v2 - Shared memory with agent overlays

Usage:
    from amem_client import AMEMClient
    
    # Each agent has its own ID but shares user profile
    memory = AMEMClient("http://localhost:8080", agent_id="claude")
    
    # Auto-detects scope: preferences/facts go to shared, notes go to private
    memory.remember("User prefers Python")  # Shared (all agents see)
    memory.remember("My plan for this task", scope="private")  # Only Claude
    
    # Recall merges shared + private
    results = memory.recall("programming")
    # Returns: [{content: "...", source: "shared"}, {content: "...", source: "private"}]
"""
import requests
import json
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class MemoryResult:
    content: str
    source: str  # "shared" or "private"
    confidence: float


class AMEMClient:
    """
    Universal AMEM client with shared memory support.
    
    Memory Scopes:
    - "shared": All agents can read (user preferences, facts)
    - "private": Only this agent (working notes, temporary)
    - "auto": Decide based on content type (default)
    - "both": Store in both scopes
    """
    
    def __init__(self, base_url: str = "http://localhost:8080", 
                 agent_id: str = "default",
                 default_scope: str = "auto"):
        self.base_url = base_url.rstrip('/')
        self.agent_id = agent_id
        self.default_scope = default_scope
        self._session = requests.Session()
    
    def _post(self, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        response = self._session.post(url, json={**data, "agent_id": self.agent_id}, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def remember(self, content: str, memory_type: str = "fact",
                 importance: float = 0.5, scope: str = None,
                 tags: List[str] = None) -> Dict:
        """
        Store memory with automatic scope detection.
        
        Scope:
            - "shared": User preferences, facts (all agents benefit)
            - "private": Working notes, temporary context
            - "auto": Let AMEM decide (default)
            - "both": Store in both
        
        Auto-detection rules:
            - preference/fact/skill -> shared
            - episode/note -> private
            - "user prefers/likes/wants" -> shared
        """
        result = self._post('/api/remember', {
            'content': content,
            'type': memory_type,
            'importance': importance,
            'scope': scope or self.default_scope,
            'tags': tags or []
        })
        return result
    
    def recall(self, query: str, k: int = 5,
               sources: List[str] = None) -> List[MemoryResult]:
        """
        Search memory.
        
        Sources:
            - ["shared"]: Only shared user profile
            - ["private"]: Only this agent's memories
            - ["both"] or None: Merged results (default)
        
        Returns list with source attribution.
        """
        result = self._post('/api/recall', {
            'query': query,
            'k': k,
            'sources': sources or ['both']
        })
        
        return [
            MemoryResult(r['content'], r['source'], r.get('confidence', 1.0))
            for r in result.get('results', [])
        ]
    
    def get_context(self, query: str = "", max_tokens: int = 1500) -> Dict[str, str]:
        """
        Get full context for this agent.
        
        Returns:
            {
                "shared": "User profile (all agents see this)",
                "private": "Your private notes",
                "working": "Current session context",
                "formatted": "Combined formatted for prompts"
            }
        """
        result = self._post('/api/context', {
            'query': query,
            'max_tokens': max_tokens
        })
        return {
            'shared': result.get('shared', ''),
            'private': result.get('private', ''),
            'working': result.get('working', ''),
            'formatted': result.get('formatted', '')
        }
    
    def get_prompt_context(self, task: str = "", max_tokens: int = 1500) -> str:
        """
        Get formatted context ready to inject into prompts.
        
        Usage:
            context = memory.get_prompt_context("coding task")
            system_prompt = f"{context}\n\nYou are a helpful assistant..."
        """
        ctx = self.get_context(task, max_tokens)
        return ctx.get('formatted', '')
    
    def extract(self, text: str, assistant_response: str = "") -> List[Dict]:
        """
        Extract facts from text and auto-store with appropriate scope.
        
        Facts are automatically categorized:
        - preferences/facts/skills -> shared
        - other -> private
        """
        result = self._post('/api/extract', {
            'text': text,
            'assistant': assistant_response
        })
        return result.get('stored', [])
    
    def process_turn(self, user_message: str, assistant_response: str) -> List[Dict]:
        """Process conversation turn - extract and store facts."""
        return self.extract(user_message, assistant_response)
    
    def publish(self, content: str, memory_type: str = "fact") -> bool:
        """
        Explicitly share a private thought with all agents.
        
        Use this when you want other agents to know something
        you discovered or decided.
        """
        result = self._post('/api/publish', {
            'content': content,
            'type': memory_type
        })
        return result.get('success', False)
    
    def query_shared(self, query: str, k: int = 5) -> List[MemoryResult]:
        """Direct query to shared memory (all agents' shared data)."""
        result = self._post('/api/shared/query', {
            'query': query,
            'k': k
        })
        return [
            MemoryResult(r['content'], 'shared', r.get('confidence', 1.0))
            for r in result.get('results', [])
        ]
    
    def stats(self) -> Dict:
        """Get memory statistics for this agent and shared."""
        return self._post('/api/stats', {})
    
    def working_remember(self, content: str):
        """
        Store in working memory (session only).
        
        Not persisted - use for temporary context.
        """
        # Working memory is handled server-side per session
        # For now, store as private with note type
        return self.remember(content, memory_type="note", scope="private")


# CLI usage
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("AMEM Client - Shared Memory with Agent Overlays")
        print("")
        print("Usage: amem_client.py [command] [args...]")
        print("")
        print("Commands:")
        print("  remember 'content' [--shared|--private]   Store memory")
        print("  recall 'query'                            Search memories")
        print("  context [task]                            Get full context")
        print("  stats                                     Show statistics")
        print("")
        print("Environment:")
        print("  AMEM_URL=http://localhost:8080")
        print("  AMEM_AGENT_ID=default")
        sys.exit(1)
    
    url = os.getenv('AMEM_URL', 'http://localhost:8080')
    agent = os.getenv('AMEM_AGENT_ID', 'default')
    client = AMEMClient(url, agent)
    
    cmd = sys.argv[1]
    
    if cmd == "remember" and len(sys.argv) >= 3:
        content = sys.argv[2]
        scope = "auto"
        if "--shared" in sys.argv:
            scope = "shared"
        elif "--private" in sys.argv:
            scope = "private"
        
        result = client.remember(content, scope=scope)
        if result.get("stored"):
            print(f"✓ Stored ({result.get('scope', 'auto')})")
            if result.get("shared"):
                print("  → Shared (all agents can see)")
            if result.get("private"):
                print("  → Private (only you)")
        else:
            print("✗ Failed")
    
    elif cmd == "recall" and len(sys.argv) >= 3:
        query = sys.argv[2]
        results = client.recall(query)
        for r in results:
            icon = "🌐" if r.source == "shared" else "🔒"
            print(f"{icon} [{r.source}] {r.content}")
    
    elif cmd == "context":
        task = sys.argv[2] if len(sys.argv) > 2 else ""
        ctx = client.get_context(task)
        print("=== Shared (User Profile) ===")
        print(ctx['shared'] or "(empty)")
        print("\n=== Private (Your Notes) ===")
        print(ctx['private'] or "(empty)")
        print("\n=== Working (Session) ===")
        print(ctx['working'] or "(empty)")
    
    elif cmd == "stats":
        print(json.dumps(client.stats(), indent=2))
    
    else:
        print(f"Unknown command: {cmd}")