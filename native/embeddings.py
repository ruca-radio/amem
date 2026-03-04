#!/usr/bin/env python3
"""
Multi-Provider Embedding Service for OpenClaw Memory System
Supports: Ollama (local), HuggingFace (local), OpenAI (cloud)
Auto-fallback chain: Ollama → HuggingFace → OpenAI
"""
import hashlib
import json
import math
import os
import random
import subprocess
import urllib.request
import urllib.error
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict, Any

# Provider configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
HF_MODEL = os.getenv("HF_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Default dimension (nomic-embed-text)
DEFAULT_DIM = 768


class EmbeddingProvider:
    """Base class for embedding providers"""
    
    def __init__(self, name: str):
        self.name = name
        self.available = False
        self.dim = DEFAULT_DIM
        self._check_available()
    
    def _check_available(self):
        """Override to check if provider is available"""
        pass
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts. Returns list of embeddings."""
        raise NotImplementedError


class OllamaProvider(EmbeddingProvider):
    """Ollama local embedding provider"""
    
    def __init__(self):
        self.name = "ollama"
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.available = False
        self.dim = DEFAULT_DIM
        self._check_available()
    
    def _check_available(self):
        """Check if Ollama is running and model is available"""
        try:
            req = urllib.request.Request(
                f"{self.host}/api/tags",
                method="GET",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if our model is available
                    if any(self.model in m for m in models):
                        self.available = True
                        print(f"[Embeddings] Ollama available with {self.model}")
                    else:
                        print(f"[Embeddings] Ollama running but {self.model} not found")
        except Exception as e:
            print(f"[Embeddings] Ollama not available: {e}")
    
    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text via Ollama API"""
        payload = json.dumps({
            "model": self.model,
            "prompt": text
        }).encode()
        
        req = urllib.request.Request(
            f"{self.host}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data["embedding"]
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts with caching"""
        embeddings = []
        for text in texts:
            embedding = self._cached_embed(text)
            embeddings.append(embedding)
        return embeddings
    
    @lru_cache(maxsize=10000)
    def _cached_embed(self, text: str) -> tuple:
        """Cached embedding for single text - returns tuple for hashability"""
        return tuple(self._embed_single(text))


class HuggingFaceProvider(EmbeddingProvider):
    """HuggingFace local embedding via transformers (if available)"""
    
    def __init__(self):
        self.name = "huggingface"
        self.model_name = HF_MODEL
        self.available = False
        self.dim = 384  # MiniLM default
        self._pipeline = None
        self._check_available()
    
    def _check_available(self):
        """Check if transformers and torch are available"""
        try:
            import importlib.util
            if importlib.util.find_spec("transformers") and importlib.util.find_spec("torch"):
                self.available = True
                print(f"[Embeddings] HuggingFace available with {self.model_name}")
        except Exception as e:
            print(f"[Embeddings] HuggingFace not available: {e}")
    
    def _load_model(self):
        """Lazy load the model"""
        if self._pipeline is None:
            from transformers import pipeline
            print(f"[Embeddings] Loading HuggingFace model: {self.model_name}")
            self._pipeline = pipeline(
                "feature-extraction",
                model=self.model_name,
                device=-1  # CPU
            )
            # Get actual dimension from model
            # MiniLM-L6-v2 is 384-dim
            if "mini" in self.model_name.lower():
                self.dim = 384
        return self._pipeline
    
    def _embed_single(self, text: str) -> List[float]:
        """Embed a single text via HuggingFace"""
        pipeline = self._load_model()
        # Get embeddings (shape: [1, seq_len, hidden_dim])
        result = pipeline(text, return_tensors=True)
        # Mean pool across sequence dimension
        embedding = result[0].mean(dim=1).squeeze().tolist()
        return embedding
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts with caching"""
        embeddings = []
        for text in texts:
            embedding = self._cached_embed(text)
            embeddings.append(embedding)
        return embeddings
    
    @lru_cache(maxsize=10000)
    def _cached_embed(self, text: str) -> tuple:
        """Cached embedding for single text - returns tuple for hashability"""
        return tuple(self._embed_single(text))


class OpenAIProvider(EmbeddingProvider):
    """OpenAI cloud embedding provider"""
    
    def __init__(self):
        self.name = "openai"
        self.api_key = OPENAI_KEY
        self.model = OPENAI_MODEL
        self.available = False
        self.dim = 1536  # text-embedding-3-small
        self._check_available()
    
    def _check_available(self):
        """Check if OpenAI API key is configured"""
        if self.api_key:
            self.available = True
            print(f"[Embeddings] OpenAI available with {self.model}")
    
    def _embed_batch_raw(self, texts: List[str]) -> List[List[float]]:
        """Raw batch embedding via OpenAI API"""
        import urllib.request
        import urllib.error
        
        payload = json.dumps({
            "input": texts,
            "model": self.model
        }).encode()
        
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            # Sort by index to maintain order
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [e["embedding"] for e in embeddings]
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts with caching"""
        # Check cache for each text
        cached_results = {}
        texts_to_embed = []
        indices = []
        
        for i, text in enumerate(texts):
            cached = self._get_cached(text)
            if cached is not None:
                cached_results[i] = cached
            else:
                texts_to_embed.append(text)
                indices.append(i)
        
        # Batch embed uncached texts
        if texts_to_embed:
            new_embeddings = self._embed_batch_raw(texts_to_embed)
            for idx, text, embedding in zip(indices, texts_to_embed, new_embeddings):
                self._set_cached(text, embedding)
                cached_results[idx] = embedding
        
        # Return in original order
        return [cached_results[i] for i in range(len(texts))]
    
    def _get_cached(self, text: str) -> Optional[List[float]]:
        """Get cached embedding if exists"""
        key = hashlib.sha256(f"{self.model}:{text}".encode()).hexdigest()
        # Simple in-memory cache for OpenAI (lru_cache not suitable for batch)
        if not hasattr(self, '_cache'):
            self._cache = {}
        return self._cache.get(key)
    
    def _set_cached(self, text: str, embedding: List[float]):
        """Cache embedding with LRU eviction"""
        key = hashlib.sha256(f"{self.model}:{text}".encode()).hexdigest()
        if not hasattr(self, '_cache'):
            self._cache = {}
            self._cache_order = []
        
        # Evict oldest if at capacity
        if key not in self._cache and len(self._cache) >= 10000:
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]
        
        self._cache[key] = embedding
        if key in self._cache_order:
            self._cache_order.remove(key)
        self._cache_order.append(key)


class SimpleHashEmbedding:
    """Fallback: deterministic hash-based embeddings (no ML)"""
    
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.name = "hash-fallback"
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Create deterministic pseudo-embeddings"""
        embeddings = []
        
        for text in texts:
            # Hash-based random projection
            h = hashlib.sha256(text.encode()).hexdigest()
            random.seed(int(h, 16))
            
            vec = []
            for _ in range(self.dim):
                u1 = random.random()
                u2 = random.random()
                z = math.sqrt(-2 * math.log(u1 + 1e-10)) * math.cos(2 * math.pi * u2)
                vec.append(z)
            
            # Normalize
            norm = math.sqrt(sum(x*x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            
            embeddings.append(vec)
        
        return embeddings


class MultiProviderEmbedding:
    """
    Multi-provider embedding with automatic fallback.
    Priority: HuggingFace → Ollama → OpenAI → Hash Fallback
    """
    
    def __init__(self, preferred: Optional[str] = None):
        self.providers: Dict[str, EmbeddingProvider] = {}
        self.fallback = SimpleHashEmbedding()
        self.active_provider: Optional[EmbeddingProvider] = None
        
        # Initialize providers
        self.providers["huggingface"] = HuggingFaceProvider()
        self.providers["ollama"] = OllamaProvider()
        self.providers["openai"] = OpenAIProvider()
        
        # Select active provider
        if preferred and preferred in self.providers:
            if self.providers[preferred].available:
                self.active_provider = self.providers[preferred]
        
        # Auto-select if no preference: HuggingFace first for best quality/speed
        if self.active_provider is None:
            for name in ["huggingface", "ollama", "openai"]:
                if self.providers[name].available:
                    self.active_provider = self.providers[name]
                    break
        
        if self.active_provider:
            print(f"[Embeddings] Using provider: {self.active_provider.name}")
            self.dim = self.active_provider.dim
        else:
            print(f"[Embeddings] No ML provider available, using hash fallback")
            self.dim = self.fallback.dim
    
    def embed(self, text: str) -> List[float]:
        """Embed single text"""
        return self.embed_batch([text])[0]
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        if not texts:
            return []
        
        if self.active_provider:
            try:
                return self.active_provider.embed(texts)
            except Exception as e:
                print(f"[Embeddings] Provider {self.active_provider.name} failed: {e}")
                print("[Embeddings] Falling back to hash embedding")
        
        return self.fallback.embed(texts)
    
    def get_info(self) -> Dict[str, Any]:
        """Get provider information"""
        return {
            "active": self.active_provider.name if self.active_provider else "hash-fallback",
            "dimension": self.dim,
            "available": {
                name: provider.available 
                for name, provider in self.providers.items()
            }
        }


# Singleton instance
_embedder: Optional[MultiProviderEmbedding] = None

def get_embedder(preferred: Optional[str] = None) -> MultiProviderEmbedding:
    """Get or create global embedder instance"""
    global _embedder
    if _embedder is None or preferred:
        _embedder = MultiProviderEmbedding(preferred)
    return _embedder


# Demo
if __name__ == "__main__":
    print("Multi-Provider Embedding Service")
    print("=" * 50)
    
    embedder = get_embedder()
    info = embedder.get_info()
    print(f"\nProvider: {info['active']}")
    print(f"Dimension: {info['dimension']}")
    print(f"Available: {info['available']}")
    
    # Test embedding
    texts = [
        "OpenClaw is a multi-channel AI gateway",
        "Memory systems help agents remember context",
        "Vector embeddings enable semantic search"
    ]
    
    print(f"\nEmbedding {len(texts)} texts...")
    embeddings = embedder.embed_batch(texts)
    
    for i, (text, emb) in enumerate(zip(texts, embeddings)):
        print(f"\n{i+1}. {text[:50]}...")
        print(f"   Embedding dim: {len(emb)}")
        print(f"   First 5 values: {[round(x, 4) for x in emb[:5]]}")
    
    # Test similarity
    if len(embeddings) >= 2:
        import math
        def cosine_sim(a, b):
            dot = sum(x*y for x, y in zip(a, b))
            na = math.sqrt(sum(x*x for x in a))
            nb = math.sqrt(sum(x*x for x in b))
            return dot / (na * nb) if na > 0 and nb > 0 else 0.0
        
        print(f"\nSimilarities:")
        print(f"  Text 1 ↔ Text 2: {cosine_sim(embeddings[0], embeddings[1]):.4f}")
        print(f"  Text 1 ↔ Text 3: {cosine_sim(embeddings[0], embeddings[2]):.4f}")
        print(f"  Text 2 ↔ Text 3: {cosine_sim(embeddings[1], embeddings[2]):.4f}")