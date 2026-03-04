#!/usr/bin/env python3
"""
AMEM Bridge for OpenClaw Plugin
Simple JSON-over-stdio bridge between TypeScript plugin and Python AMEM.
"""
import json
import sys
import os
from pathlib import Path

# Add AMEM to path
home = Path.home()
amem_paths = [
    home / ".openclaw" / "workspace" / "memory_system",
    home / ".openclaw" / "workspace" / "memory-system" / "native",
]

for path in amem_paths:
    if str(path) not in sys.path and path.exists():
        sys.path.insert(0, str(path))

try:
    from openclaw_memory import MemoryTools
    from auto_extract import AutoMemoryExtractor
    from graph_memory import MemoryGraphTools
except ImportError as e:
    print(json.dumps({"error": f"AMEM not installed: {e}"}), file=sys.stderr)
    sys.exit(1)


class AMEMBridge:
    def __init__(self, config):
        self.agent_id = config.get("agentId", "default")
        self.memory = MemoryTools(self.agent_id)
        self.extractor = AutoMemoryExtractor(self.agent_id)
        self.graph = MemoryGraphTools(self.agent_id)
    
    def handle_request(self, request):
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("_requestId")
        
        try:
            if method == "remember":
                result = self.memory.remember(
                    content=params.get("content"),
                    permanent=params.get("permanent", False)
                )
                return {"_requestId": req_id, "success": True, "result": result}
            
            elif method == "recall":
                results = self.memory.recall(
                    query=params.get("query"),
                    k=params.get("k", 5)
                )
                return {"_requestId": req_id, "success": True, "results": results}
            
            elif method == "graph_query":
                results = self.graph.graph.query(params.get("entity"))
                return {"_requestId": req_id, "success": True, "results": results}
            
            elif method == "ask":
                answer = self.graph.ask(params.get("question"))
                return {"_requestId": req_id, "success": True, "answer": answer}
            
            else:
                return {"_requestId": req_id, "success": False, "error": f"Unknown method: {method}"}
        
        except Exception as e:
            return {"_requestId": req_id, "success": False, "error": str(e)}


def main():
    # Read config from first line
    config_line = sys.stdin.readline()
    try:
        config = json.loads(config_line)
    except:
        config = {}
    
    bridge = AMEMBridge(config)
    
    # Process requests
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = bridge.handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()