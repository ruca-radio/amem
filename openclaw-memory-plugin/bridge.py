#!/usr/bin/env python3
"""
OpenClaw Memory Plugin - Python Bridge
Connects OpenClaw Node.js runtime to Python memory system.
"""
import json
import sys
import os
from pathlib import Path

# Add memory system to path
NATIVE_DIR = Path(__file__).parent.parent / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools
from auto_extract import AutoMemoryExtractor
from graph_memory import MemoryGraphTools


class MemoryPluginBridge:
    """Bridge between OpenClaw and Python memory system"""
    
    def __init__(self, config: dict):
        self.agent_id = config.get("agentId", "default")
        self.embedding_provider = config.get("embeddingProvider", "auto")
        self.auto_extract = config.get("autoExtract", True)
        self.graph_enabled = config.get("graphMemory", True)
        
        # Initialize memory systems
        self.memory = MemoryTools(self.agent_id)
        self.extractor = AutoMemoryExtractor(self.agent_id)
        self.graph = MemoryGraphTools(self.agent_id) if self.graph_enabled else None
    
    def remember(self, content: str, permanent: bool = False, **kwargs) -> dict:
        """Store a memory"""
        result = self.memory.remember(content, permanent=permanent)
        
        # Also extract entities if graph enabled
        if self.graph_enabled:
            self.graph.remember(content, extract_entities=True, permanent=permanent)
        
        return {"success": True, "result": result}
    
    def recall(self, query: str, k: int = 5, **kwargs) -> dict:
        """Search memories"""
        results = self.memory.recall(query, k=k)
        return {"success": True, "results": results}
    
    def context(self, query: str, max_tokens: int = 1500, **kwargs) -> dict:
        """Get context for prompts"""
        context = self.memory.context_for_prompt(query, max_tokens)
        return {"success": True, "context": context}
    
    def graph_query(self, entity: str, **kwargs) -> dict:
        """Query graph memory"""
        if not self.graph:
            return {"success": False, "error": "Graph memory disabled"}
        
        results = self.graph.graph.query(entity)
        return {"success": True, "results": results}
    
    def extract(self, text: str, **kwargs) -> dict:
        """Extract facts from text"""
        facts = self.extractor.extractor.extract(text)
        return {
            "success": True,
            "facts": [
                {
                    "content": f.content,
                    "type": f.fact_type,
                    "confidence": f.confidence
                }
                for f in facts
            ]
        }
    
    def process_conversation(self, user_msg: str, assistant_msg: str, **kwargs) -> dict:
        """Process conversation turn and extract memories"""
        if not self.auto_extract:
            return {"success": True, "extracted": 0}
        
        facts = self.extractor.process_turn(user_msg, assistant_msg)
        return {
            "success": True,
            "extracted": len(facts),
            "facts": [f.content for f in facts]
        }
    
    def stats(self, **kwargs) -> dict:
        """Get memory statistics"""
        return {
            "success": True,
            "stats": self.memory.store.stats()
        }


def main():
    """Main entry point - called by OpenClaw plugin system"""
    # Read config from stdin (passed by OpenClaw)
    config = json.loads(sys.stdin.read())
    
    bridge = MemoryPluginBridge(config)
    
    # Read commands from stdin, one per line
    for line in sys.stdin:
        try:
            cmd = json.loads(line)
            method = cmd.get("method")
            params = cmd.get("params", {})
            
            if hasattr(bridge, method):
                result = getattr(bridge, method)(**params)
                print(json.dumps(result))
                sys.stdout.flush()
            else:
                print(json.dumps({"success": False, "error": f"Unknown method: {method}"}))
                sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()