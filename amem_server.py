#!/usr/bin/env python3
"""
AMEM Server v2 - Shared memory with agent overlays

Architecture:
- SHARED: Core facts, preferences, user profile (all agents read)
- AGENT: Agent-specific context, working memory (private to agent)
- DYNAMIC: Runtime sharing - agents can publish to shared, subscribe to topics

Benefits:
- All agents know user preferences (shared)
- Each agent has private working space
- Dynamic collaboration when needed
"""
import json
import asyncio
import websockets
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import logging
import sys
import os
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('amem')

MIN_CONTEXT_TOKENS = 1
MAX_CONTEXT_TOKENS = 8000

# Import AMEM
NATIVE_DIR = Path(__file__).parent / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, WORKSPACE_DIR
from auto_extract import AutoMemoryExtractor
from graph_memory import MemoryGraphTools

# Import security patches
from security_patch import (
    SecurityManager, InputValidator, SafeErrorHandler,
    AuthenticationError, AuthorizationError, ValidationError
)

# Initialize security manager
security = SecurityManager()


class SharedMemoryLayer:
    """
    Shared memory accessible by all agents.
    Stores: user preferences, facts, skills, decisions
    """
    def __init__(self):
        self.memory = MemoryTools("shared")
        self.graph = MemoryGraphTools("shared")
        self.lock = threading.RLock()
    
    def remember(self, content: str, memory_type: str = "fact", 
                 importance: float = 0.5, tags: List[str] = None) -> bool:
        """Store in shared memory (thread-safe)"""
        with self.lock:
            return self.memory.remember(
                content=content,
                memory_type=memory_type,
                importance=importance,
                permanent=True  # Shared is always permanent
            )
    
    def recall(self, query: str, k: int = 5, 
               memory_types: List[str] = None) -> List[Dict]:
        """Search shared memory"""
        with self.lock:
            results = self.memory.recall(query, k=k)
            # Return enriched results
            return [{"content": r, "source": "shared", "confidence": 1.0} for r in results]
    
    def ask(self, question: str) -> str:
        """Ask shared graph memory"""
        with self.lock:
            return self.graph.ask(question)
    
    def get_context(self, query: str, max_tokens: int = 1000) -> str:
        """Get shared context for prompts"""
        with self.lock:
            return self.memory.context_for_prompt(query, max_tokens)
    
    def stats(self) -> Dict:
        """Shared memory stats"""
        with self.lock:
            return self.memory.store.stats()


class AgentMemoryLayer:
    """
    Agent-specific memory overlay.
    Stores: working context, temporary state, agent-specific notes
    """
    def __init__(self, agent_id: str, shared: SharedMemoryLayer):
        self.agent_id = agent_id
        self.shared = shared
        self.private = MemoryTools(agent_id)
        self.extractor = AutoMemoryExtractor(agent_id)
        self.graph = MemoryGraphTools(agent_id)
        self.working_memory: List[str] = []  # Session-only
        self.subscribed_topics: Set[str] = set()
        self.last_access = datetime.now()
    
    def touch(self):
        """Update last access time"""
        self.last_access = datetime.now()
    
    def remember(self, content: str, memory_type: str = "fact",
                 importance: float = 0.5, scope: str = "auto",
                 tags: List[str] = None) -> Dict:
        """
        Store memory with scope control.
        
        scope:
            "shared" - All agents can see
            "private" - Only this agent
            "auto" - Decide based on content
        """
        self.touch()
        
        # Auto-detect scope if not specified
        if scope == "auto":
            scope = self._detect_scope(content, memory_type)
        
        result = {
            "stored": False,
            "scope": scope,
            "shared": False,
            "private": False
        }
        
        if scope in ["shared", "both"]:
            # Store in shared (all agents benefit)
            result["shared"] = self.shared.remember(
                content=f"[{self.agent_id}] {content}" if scope == "both" else content,
                memory_type=memory_type,
                importance=importance,
                tags=tags
            )
        
        if scope in ["private", "both"]:
            # Store in private (agent-specific)
            result["private"] = self.private.remember(
                content=content,
                memory_type=memory_type,
                importance=importance,
                permanent=False  # Agent memory is ephemeral by default
            )
        
        result["stored"] = result["shared"] or result["private"]
        return result
    
    def _detect_scope(self, content: str, memory_type: str) -> str:
        """Auto-detect if memory should be shared or private"""
        # User preferences/facts/skills -> shared (all agents need to know)
        if memory_type in ["preference", "fact", "skill"]:
            return "shared"
        
        # Working notes, temporary context -> private
        if memory_type in ["episode", "note"]:
            return "private"
        
        # Check content patterns
        shared_patterns = [
            "user prefers", "user likes", "user wants",
            "user works at", "user uses", "user knows",
            "decided to", "chose to", "will use"
        ]
        
        content_lower = content.lower()
        for pattern in shared_patterns:
            if pattern in content_lower:
                return "shared"
        
        return "private"
    
    def recall(self, query: str, k: int = 5, 
               sources: List[str] = None) -> List[Dict]:
        """
        Search memory with source control.
        
        sources:
            ["shared"] - Only shared memory
            ["private"] - Only agent memory
            ["both"] or None - Both merged
        """
        self.touch()
        
        if sources is None:
            sources = ["both"]
        
        results = []
        k_per_source = max(1, k // 2) if "both" in sources else k
        
        if "shared" in sources or "both" in sources:
            shared_results = self.shared.recall(query, k=k_per_source)
            for r in shared_results:
                r["source"] = "shared"
            results.extend(shared_results)
        
        if "private" in sources or "both" in sources:
            private_results = self.private.recall(query, k=k_per_source)
            for r in private_results:
                r["source"] = "private"
                r["confidence"] = 0.9  # Slightly lower than shared
            results.extend([{"content": r, "source": "private", "confidence": 0.9} 
                          for r in private_results])
        
        # Sort by relevance (simplified - in real impl use scores)
        return results[:k]
    
    def working_remember(self, content: str):
        """Store in working memory (session only, not persisted)"""
        self.touch()
        self.working_memory.append({
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 50
        self.working_memory = self.working_memory[-50:]
    
    def get_full_context(self, query: str, max_tokens: int = 1500) -> Dict:
        """
        Get complete context for this agent:
        - Shared user profile
        - Agent's private memories
        - Working session memory
        """
        self.touch()
        
        # Shared context (all agents see this)
        shared_ctx = self.shared.get_context(query, max_tokens // 3)
        
        # Private context (agent-specific)
        private_ctx = self.private.context_for_prompt(query, max_tokens // 3)
        
        # Working memory (session only)
        working_ctx = ""
        if self.working_memory:
            working_ctx = "## Current Session\n" + "\n".join(
                f"- {m['content']}" for m in self.working_memory[-10:]
            )
        
        return {
            "shared": shared_ctx,
            "private": private_ctx,
            "working": working_ctx,
            "formatted": self._format_context(shared_ctx, private_ctx, working_ctx)
        }
    
    def _format_context(self, shared: str, private: str, working: str) -> str:
        """Format context for prompt injection"""
        parts = []
        if shared:
            parts.append(f"## User Profile (Shared)\n{shared}")
        if private:
            parts.append(f"## Your Notes (Private)\n{private}")
        if working:
            parts.append(working)
        return "\n\n".join(parts)
    
    def extract_and_store(self, user_msg: str, assistant_msg: str = "") -> List[Dict]:
        """Extract facts and store appropriately"""
        self.touch()
        
        facts = self.extractor.process_turn(user_msg, assistant_msg)
        stored = []
        
        for fact in facts:
            # Auto-determine scope based on fact type
            scope = "shared" if fact.fact_type in ["preference", "fact", "skill"] else "private"
            
            result = self.remember(
                content=fact.content,
                memory_type=fact.fact_type,
                importance=fact.confidence,
                scope=scope
            )
            
            stored.append({
                "content": fact.content,
                "type": fact.fact_type,
                "scope": scope,
                "confidence": fact.confidence,
                "stored": result["stored"]
            })
        
        return stored
    
    def publish_to_shared(self, content: str, memory_type: str = "fact"):
        """Explicitly share a private memory with all agents"""
        return self.shared.remember(
            content=f"[{self.agent_id} shares] {content}",
            memory_type=memory_type,
            importance=0.8
        )
    
    def subscribe(self, topic: str):
        """Subscribe to a topic for updates"""
        self.subscribed_topics.add(topic)
    
    def stats(self) -> Dict:
        """Get stats for this agent"""
        return {
            "agent_id": self.agent_id,
            "private": self.private.store.stats(),
            "working_memory_items": len(self.working_memory),
            "subscribed_topics": list(self.subscribed_topics)
        }


class AMEMRegistry:
    """Registry of all agents"""
    def __init__(self):
        self.shared = SharedMemoryLayer()
        self.agents: Dict[str, AgentMemoryLayer] = {}
        self.lock = threading.RLock()
        self.subscribers: Dict[str, Set[str]] = {}  # topic -> agent_ids
    
    def get_agent(self, agent_id: str) -> AgentMemoryLayer:
        """Get or create agent"""
        with self.lock:
            if agent_id not in self.agents:
                logger.info(f"Creating agent: {agent_id}")
                self.agents[agent_id] = AgentMemoryLayer(agent_id, self.shared)
            return self.agents[agent_id]
    
    def cleanup_inactive(self, max_age_minutes: int = 30):
        """Remove agents inactive for too long"""
        cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
        with self.lock:
            to_remove = [
                aid for aid, agent in self.agents.items()
                if agent.last_access < cutoff
            ]
            for aid in to_remove:
                logger.info(f"Cleaning up inactive agent: {aid}")
                del self.agents[aid]
    
    def list_agents(self) -> List[Dict]:
        """List all active agents"""
        with self.lock:
            return [
                {
                    "id": aid,
                    "last_access": agent.last_access.isoformat(),
                    "topics": list(agent.subscribed_topics)
                }
                for aid, agent in self.agents.items()
            ]
    
    def broadcast(self, topic: str, message: Dict, exclude_agent: str = None):
        """Broadcast message to all agents subscribed to topic"""
        with self.lock:
            subscribers = self.subscribers.get(topic, set())
            for agent_id in subscribers:
                if agent_id != exclude_agent and agent_id in self.agents:
                    agent = self.agents[agent_id]
                    # Could trigger notification here
                    logger.debug(f"Notifying {agent_id} about {topic}")


# Global registry
registry = AMEMRegistry()
websocket_clients: Set[websockets.WebSocketServerProtocol] = set()

# Connection pool for HTTP requests
_session: Optional[requests.Session] = None

def get_session() -> requests.Session:
    """Get or create a requests session with connection pooling"""
    global _session
    if _session is None:
        _session = requests.Session()
        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


class AMEMAPIHandler(BaseHTTPRequestHandler):
    """HTTP API Handler with security fixes"""
    
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")
    
    def send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.end_headers()
    
    def _get_api_key(self) -> Optional[str]:
        """Extract API key from headers"""
        return self.headers.get('X-API-Key')
    
    def _authenticate(self, agent_id: str) -> bool:
        """Authenticate request using API key"""
        api_key = self._get_api_key()
        if not api_key:
            return False
        try:
            return security.authenticate(agent_id, api_key)
        except AuthenticationError:
            return False
    
    def do_GET(self):
        # Public endpoints don't require auth
        if self.path == '/':
            self.send_json({
                "amem": "Agent Memory System",
                "version": "2.0",
                "features": ["shared_memory", "agent_overlays", "dynamic_sharing"],
                "security": "enabled"
            })
        elif self.path == '/api/agents':
            self.send_json({"agents": registry.list_agents()})
        elif self.path == '/health':
            self.send_json({"status": "ok"})
        else:
            self.send_json({'error': 'Not found', 'code': 'NOT_FOUND'}, 404)
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except:
            self.send_json({'error': 'Invalid JSON', 'code': 'INVALID_JSON'}, 400)
            return
        
        agent_id = data.get('agent_id', 'default')
        
        # Authenticate all POST requests
        if not self._authenticate(agent_id):
            self.send_json({'error': 'Authentication failed', 'code': 'AUTH_FAILED'}, 401)
            return
        
        # Validate agent_id format
        try:
            if not security._is_valid_agent_id(agent_id):
                self.send_json({'error': 'Invalid agent_id format', 'code': 'VALIDATION_ERROR'}, 400)
                return
        except Exception:
            self.send_json({'error': 'Invalid agent_id format', 'code': 'VALIDATION_ERROR'}, 400)
            return
        
        agent = registry.get_agent(agent_id)
        path = self.path
        
        try:
            if path == '/api/remember':
                # Validate inputs
                content = InputValidator.validate_content(data.get('content', ''))
                memory_type = InputValidator.validate_memory_type(data.get('type', 'fact'))
                importance = InputValidator.validate_importance(data.get('importance', 0.5))
                scope = InputValidator.validate_scope(data.get('scope', 'auto'))
                
                result = agent.remember(
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    scope=scope,
                    tags=data.get('tags', [])
                )
                # Notify if shared
                if result.get("shared"):
                    asyncio.create_task(notify_shared_memory(agent_id, content))
            
            elif path == '/api/recall':
                query = InputValidator.validate_query(data.get('query', ''))
                k = InputValidator.validate_k(data.get('k', 5))
                
                results = agent.recall(
                    query=query,
                    k=k,
                    sources=data.get('sources', ['both'])
                )
                result = {"success": True, "results": results, "count": len(results)}
            
            elif path == '/api/context':
                query = InputValidator.validate_query(data.get('query', ''))
                try:
                    max_tokens = max(
                        MIN_CONTEXT_TOKENS,
                        min(int(data.get('max_tokens', 1500)), MAX_CONTEXT_TOKENS)
                    )
                except (ValueError, TypeError):
                    max_tokens = 1500
                
                ctx = agent.get_full_context(
                    query=query,
                    max_tokens=max_tokens
                )
                result = {"success": True, **ctx}
            
            elif path == '/api/extract':
                text = InputValidator.validate_content(data.get('text', ''))
                assistant = data.get('assistant', '')
                if assistant:
                    assistant = InputValidator.validate_content(assistant)
                
                stored = agent.extract_and_store(text, assistant)
                result = {"success": True, "stored": stored, "count": len(stored)}
            
            elif path == '/api/publish':
                content = InputValidator.validate_content(data.get('content', ''))
                mem_type = InputValidator.validate_memory_type(data.get('type', 'fact'))
                
                success = agent.publish_to_shared(content, mem_type)
                result = {"success": success, "published": True}
            
            elif path == '/api/stats':
                result = {
                    "success": True,
                    "agent": agent.stats(),
                    "shared": registry.shared.stats()
                }
            
            elif path == '/api/shared/query':
                # Direct shared memory access
                query = InputValidator.validate_query(data.get('query', ''))
                k = InputValidator.validate_k(data.get('k', 5))
                
                results = registry.shared.recall(query, k=k)
                result = {"success": True, "results": results}
            
            else:
                self.send_json({'error': 'Unknown endpoint', 'code': 'NOT_FOUND'}, 404)
                return
            
            self.send_json(result)
            
        except ValidationError as e:
            status, response = SafeErrorHandler.handle_error(e)
            self.send_json(response, status)
        except Exception as e:
            logger.exception("API error")
            is_dev = os.getenv('AMEM_ENV', 'production') == 'development'
            status, response = SafeErrorHandler.handle_error(e, is_dev)
            self.send_json(response, status)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


async def notify_shared_memory(agent_id: str, content: str):
    """Notify all agents of new shared memory"""
    message = json.dumps({
        "type": "shared_memory_added",
        "by_agent": agent_id,
        "preview": content[:100] + "..." if len(content) > 100 else content,
        "timestamp": datetime.now().isoformat()
    })
    
    dead = set()
    for ws in websocket_clients:
        try:
            await ws.send(message)
        except:
            dead.add(ws)
    websocket_clients.difference_update(dead)


async def websocket_handler(websocket, path):
    """WebSocket for real-time updates with authentication"""
    logger.info(f"WS connected: {websocket.remote_address}")
    
    # Wait for authentication message
    try:
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        auth_data = json.loads(auth_msg)
        agent_id = auth_data.get('agent_id', 'default')
        api_key = auth_data.get('api_key', '')
        
        if not security.authenticate(agent_id, api_key):
            await websocket.send(json.dumps({"error": "Authentication failed"}))
            await websocket.close(1008, "Authentication failed")
            return
        
        await websocket.send(json.dumps({"type": "authenticated"}))
        
    except asyncio.TimeoutError:
        await websocket.close(1008, "Authentication timeout")
        return
    except Exception as e:
        await websocket.close(1008, "Invalid authentication")
        return
    
    websocket_clients.add(websocket)
    
    try:
        async for message in websocket:
            data = json.loads(message)
            # Handle subscription requests
            if data.get("action") == "subscribe":
                topic = data.get("topic", "shared_memory")
                agent = registry.get_agent(agent_id)
                agent.subscribe(topic)
                await websocket.send(json.dumps({
                    "type": "subscribed",
                    "topic": topic
                }))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        websocket_clients.discard(websocket)


def run_http(port: int):
    server = ThreadedHTTPServer(('0.0.0.0', port), AMEMAPIHandler)
    logger.info(f"AMEM HTTP API on http://0.0.0.0:{port}")
    server.serve_forever()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--http-port', type=int, default=8080)
    parser.add_argument('--ws-port', type=int, default=8081)
    args = parser.parse_args()
    
    http_thread = threading.Thread(target=run_http, args=(args.http_port,), daemon=True)
    http_thread.start()
    
    logger.info(f"AMEM WebSocket on ws://0.0.0.0:{args.ws_port}")
    async with websockets.serve(websocket_handler, '0.0.0.0', args.ws_port):
        # Periodic cleanup
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            registry.cleanup_inactive()


if __name__ == '__main__':
    import argparse
    asyncio.run(main())
