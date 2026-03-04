"""
Embedding Service - Multi-provider embedding with local fallback
Supports Ollama (local), OpenAI, and any OpenAI-compatible API
"""
import os
from typing import List, Union

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Embedding Service", version="1.0.0")

# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "openrouter")
OPENAI_KEY = os.getenv("OPENAI_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")

# Model dimensions
DIMENSIONS = {
    "nomic-embed-text": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


class EmbedRequest(BaseModel):
    text: Union[str, List[str]]
    model: str = None  # Optional override
    truncate: bool = True


class EmbedResponse(BaseModel):
    embedding: List[float]
    model: str
    dimensions: int


class BatchEmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dimensions: int


async def embed_ollama(text: str, model: str = None) -> List[float]:
    """Get embedding from local Ollama"""
    model = model or OLLAMA_MODEL
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30.0
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
        except Exception as e:
            raise HTTPException(503, f"Ollama embedding failed: {e}")


async def embed_openai(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """Fallback to OpenAI embeddings"""
    if not OPENAI_KEY:
        raise HTTPException(503, "OpenAI not configured")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={"input": text, "model": model},
            timeout=30.0
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def embed_openrouter(text: str, model: str = "openai/text-embedding-3-small") -> List[float]:
    """Fallback to OpenRouter"""
    if not OPENROUTER_KEY:
        raise HTTPException(503, "OpenRouter not configured")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={"input": text, "model": model},
            timeout=30.0
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    """Single text embedding with automatic fallback"""
    text = req.text if isinstance(req.text, str) else req.text[0]
    
    # Try Ollama first (local, free)
    try:
        embedding = await embed_ollama(text, req.model)
        return EmbedResponse(
            embedding=embedding,
            model=req.model or OLLAMA_MODEL,
            dimensions=len(embedding)
        )
    except HTTPException:
        # Fallback chain
        if FALLBACK_PROVIDER == "openai" and OPENAI_KEY:
            embedding = await embed_openai(text)
            return EmbedResponse(
                embedding=embedding,
                model="text-embedding-3-small",
                dimensions=len(embedding)
            )
        elif FALLBACK_PROVIDER == "openrouter" and OPENROUTER_KEY:
            embedding = await embed_openrouter(text)
            return EmbedResponse(
                embedding=embedding,
                model="openai/text-embedding-3-small",
                dimensions=len(embedding)
            )
        raise


@app.post("/embed/batch", response_model=BatchEmbedResponse)
async def embed_batch(req: EmbedRequest):
    """Batch embedding"""
    if isinstance(req.text, str):
        texts = [req.text]
    else:
        texts = req.text
    
    # For now, sequential processing
    # Could be parallelized for production
    embeddings = []
    for text in texts:
        result = await embed(EmbedRequest(text=text, model=req.model))
        embeddings.append(result.embedding)
    
    return BatchEmbedResponse(
        embeddings=embeddings,
        model=req.model or OLLAMA_MODEL,
        dimensions=len(embeddings[0]) if embeddings else 0
    )


@app.get("/health")
async def health():
    """Health check with provider status"""
    status = {
        "ollama": False,
        "openai": bool(OPENAI_KEY),
        "openrouter": bool(OPENROUTER_KEY)
    }
    
    # Check Ollama
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            status["ollama"] = resp.status_code == 200
    except:
        pass
    
    return {
        "status": "ok" if status["ollama"] or status["openai"] or status["openrouter"] else "degraded",
        "providers": status,
        "default_model": OLLAMA_MODEL
    }


@app.get("/models")
async def list_models():
    """List available embedding models"""
    models = []
    
    # Check Ollama models
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                for m in resp.json().get("models", []):
                    name = m.get("name", "")
                    if "embed" in name.lower():
                        models.append({
                            "id": name,
                            "provider": "ollama",
                            "dimensions": DIMENSIONS.get(name, 768)
                        })
    except:
        pass
    
    # Add known cloud models
    if OPENAI_KEY:
        models.extend([
            {"id": "text-embedding-3-small", "provider": "openai", "dimensions": 1536},
            {"id": "text-embedding-3-large", "provider": "openai", "dimensions": 3072}
        ])
    
    if OPENROUTER_KEY:
        models.extend([
            {"id": "openai/text-embedding-3-small", "provider": "openrouter", "dimensions": 1536}
        ])
    
    return {"models": models}