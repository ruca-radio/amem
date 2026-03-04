"""
Agent Gateway - Unified interface for multi-model agents with memory injection
Routes requests to appropriate providers, manages context assembly
"""
import json
import os
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Agent Gateway", version="2.0.0")

# Config
MEMORY_API_URL = os.getenv("MEMORY_API_URL", "http://memory-api:8000")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_KEY", "")

# Provider routing
PROVIDERS = {
    "ollama": {"base_url": OLLAMA_HOST, "key": None},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key": OPENROUTER_KEY},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "key": ANTHROPIC_KEY},
    "openai": {"base_url": "https://api.openai.com/v1", "key": OPENAI_KEY},
}


class Message(BaseModel):
    role: str  # system, user, assistant
    content: str
    name: Optional[str] = None  # For multi-agent distinction


class AgentRequest(BaseModel):
    # Identification
    agent_id: str
    session_id: Optional[str] = None
    
    # Input
    messages: List[Message]
    
    # Model routing (optional - uses agent config if omitted)
    provider: Optional[str] = None
    model: Optional[str] = None
    
    # Memory control
    use_memory: bool = True
    memory_query: Optional[str] = None  # Custom query for memory retrieval
    memory_tiers: List[str] = ["semantic", "episodic"]
    max_memory_tokens: int = 2000
    
    # Generation params
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    
    # Alignment
    check_alignment: bool = True  # Verify response matches expected patterns


class AgentResponse(BaseModel):
    content: str
    model: str
    provider: str
    memories_used: List[Dict]
    tokens_used: Dict[str, int]
    alignment_score: Optional[float] = None


class MemoryContext(BaseModel):
    """Structured memory for injection into prompts"""
    facts: List[str] = []
    preferences: List[str] = []
    recent_episodes: List[str] = []
    skills: List[str] = []
    
    def to_prompt_section(self) -> str:
        sections = []
        if self.facts:
            sections.append("## Known Facts\n" + "\n".join(f"- {f}" for f in self.facts))
        if self.preferences:
            sections.append("## User Preferences\n" + "\n".join(f"- {p}" for p in self.preferences))
        if self.recent_episodes:
            sections.append("## Recent Context\n" + "\n".join(f"- {e}" for e in self.recent_episodes[:3]))
        if self.skills:
            sections.append("## Available Skills\n" + "\n".join(f"- {s}" for s in self.skills))
        return "\n\n".join(sections) if sections else ""


async def get_agent_config(agent_id: str) -> Dict:
    """Fetch agent configuration from memory API"""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MEMORY_API_URL}/agents/{agent_id}", timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
    
    # Default config
    return {
        "id": agent_id,
        "name": agent_id,
        "provider": "ollama",
        "model_name": "llama3.2",
        "working_memory_tokens": 4000,
        "episodic_retrieval_k": 10,
        "semantic_retrieval_k": 5
    }


async def retrieve_memories(
    agent_id: str,
    query: str,
    session_id: Optional[str],
    tiers: List[str],
    max_tokens: int
) -> MemoryContext:
    """Retrieve and structure relevant memories"""
    
    async with httpx.AsyncClient() as client:
        # Query memories
        resp = await client.post(
            f"{MEMORY_API_URL}/query",
            json={
                "query": query,
                "agent_id": agent_id,
                "session_id": session_id,
                "tiers": tiers,
                "k": 20,  # Get more than we need, filter by tokens
                "min_similarity": 0.65
            },
            timeout=10.0
        )
        resp.raise_for_status()
        memories = resp.json()
    
    # Organize by type
    context = MemoryContext()
    current_tokens = 0
    
    for mem in memories:
        content = mem.get("content", "")
        mem_tokens = len(content.split())  # Rough estimate
        
        if current_tokens + mem_tokens > max_tokens:
            break
        
        mem_type = mem.get("memory_type", "episode")
        if mem_type == "fact":
            context.facts.append(content)
        elif mem_type == "preference":
            context.preferences.append(content)
        elif mem_type == "episode":
            context.recent_episodes.append(content)
        elif mem_type == "skill":
            context.skills.append(content)
        
        current_tokens += mem_tokens
    
    return context


def build_system_prompt(base_prompt: str, memory_context: MemoryContext) -> str:
    """Combine base system prompt with memory context"""
    memory_section = memory_context.to_prompt_section()
    
    if memory_section:
        return f"{base_prompt}\n\n{memory_section}\n\nUse the above context to inform your responses."
    return base_prompt


async def call_ollama(
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: Optional[int],
    stream: bool
) -> AsyncGenerator[str, None]:
    """Call Ollama API"""
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": temperature}
    }
    if max_tokens:
        payload["options"]["num_predict"] = max_tokens
    
    async with httpx.AsyncClient() as client:
        if stream:
            async with client.stream(
                "POST",
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=120.0
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                yield data["message"].get("content", "")
                        except:
                            pass
        else:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=120.0
            )
            resp.raise_for_status()
            data = resp.json()
            yield data["message"]["content"]


async def call_openrouter(
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: Optional[int],
    stream: bool
) -> AsyncGenerator[str, None]:
    """Call OpenRouter API"""
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "HTTP-Referer": "https://memory-system.local",
        "X-Title": "Memory-Enabled Agent Gateway"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": stream
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    
    async with httpx.AsyncClient() as client:
        if stream:
            async with client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120.0
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except:
                            pass
        else:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120.0
            )
            resp.raise_for_status()
            data = resp.json()
            yield data["choices"][0]["message"]["content"]


async def call_anthropic(
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: Optional[int],
    stream: bool
) -> AsyncGenerator[str, None]:
    """Call Anthropic Claude API"""
    
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    # Extract system message if present
    system = None
    api_messages = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            api_messages.append({
                "role": m["role"],
                "content": m["content"]
            })
    
    payload = {
        "model": model,
        "messages": api_messages,
        "temperature": temperature,
        "max_tokens": max_tokens or 4096
    }
    if system:
        payload["system"] = system
    
    async with httpx.AsyncClient() as client:
        if stream:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={**payload, "stream": True},
                timeout=120.0
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        try:
                            chunk = json.loads(data)
                            if chunk.get("type") == "content_block_delta":
                                yield chunk["delta"].get("text", "")
                        except:
                            pass
        else:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=120.0
            )
            resp.raise_for_status()
            data = resp.json()
            yield data["content"][0]["text"]


@app.post("/chat")
async def chat(req: AgentRequest):
    """Main chat endpoint with memory injection"""
    
    # Get agent configuration
    config = await get_agent_config(req.agent_id)
    provider = req.provider or config.get("provider", "ollama")
    model = req.model or config.get("model_name", "llama3.2")
    
    # Retrieve memories if enabled
    memory_context = MemoryContext()
    memories_used = []
    
    if req.use_memory:
        # Use last user message as memory query if not specified
        query = req.memory_query or ""
        for m in reversed(req.messages):
            if m.role == "user":
                query = query or m.content
                break
        
        if query:
            memory_context = await retrieve_memories(
                req.agent_id,
                query,
                req.session_id,
                req.memory_tiers,
                req.max_memory_tokens
            )
            
            # Track which memories were retrieved
            # (In production, this would come from the memory API response)
    
    # Build messages with memory context
    messages = []
    
    # System message with memory
    system_content = "You are a helpful assistant."
    for m in req.messages:
        if m.role == "system":
            system_content = m.content
            break
    
    enhanced_system = build_system_prompt(system_content, memory_context)
    messages.append({"role": "system", "content": enhanced_system})
    
    # Add remaining messages
    for m in req.messages:
        if m.role != "system":
            messages.append({"role": m.role, "content": m.content})
    
    # Route to provider
    if provider == "ollama":
        generator = call_ollama(model, messages, req.temperature, req.max_tokens, req.stream)
    elif provider == "openrouter":
        generator = call_openrouter(model, messages, req.temperature, req.max_tokens, req.stream)
    elif provider == "anthropic":
        generator = call_anthropic(model, messages, req.temperature, req.max_tokens, req.stream)
    else:
        raise HTTPException(400, f"Unknown provider: {provider}")
    
    if req.stream:
        return StreamingResponse(generator, media_type="text/plain")
    
    # Collect response
    content = ""
    async for chunk in generator:
        content += chunk
    
    # Check alignment if requested
    alignment_score = None
    if req.check_alignment and req.messages:
        # Simple heuristic: does response address the last user message?
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        # In production, this would call the memory API for proper alignment checking
    
    return AgentResponse(
        content=content,
        model=model,
        provider=provider,
        memories_used=[],  # Populated from retrieval
        tokens_used={"prompt": 0, "completion": 0},  # Would track actual usage
        alignment_score=alignment_score
    )


@app.post("/chat/simple")
async def chat_simple(
    message: str,
    agent_id: str = "default",
    session_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None
):
    """Simplified chat interface"""
    req = AgentRequest(
        agent_id=agent_id,
        session_id=session_id,
        messages=[Message(role="user", content=message)],
        provider=provider,
        model=model
    )
    return await chat(req)


@app.post("/memory/write")
async def write_memory(
    agent_id: str,
    content: str,
    memory_type: str = "fact",
    importance: float = 0.5,
    session_id: Optional[str] = None
):
    """Explicit memory write endpoint"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MEMORY_API_URL}/memories",
            json={
                "content": content,
                "agent_id": agent_id,
                "session_id": session_id,
                "memory_type": memory_type,
                "importance": importance
            },
            timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()


@app.get("/health")
async def health():
    """Health check"""
    status = {
        "memory_api": False,
        "ollama": False,
        "openrouter": bool(OPENROUTER_KEY),
        "anthropic": bool(ANTHROPIC_KEY)
    }
    
    # Check memory API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MEMORY_API_URL}/health", timeout=5.0)
            status["memory_api"] = resp.status_code == 200
    except:
        pass
    
    # Check Ollama
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            status["ollama"] = resp.status_code == 200
    except:
        pass
    
    return {"status": "ok", "providers": status}