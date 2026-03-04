#!/usr/bin/env python3
"""
OpenClaw Memory System - Pure Python Implementation
No external dependencies. Integrates directly with OpenClaw.
"""
import json
import hashlib
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

MEMORY_DIR = Path("/root/.openclaw/workspace/memory-system/data")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

class MemoryTier(Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"

class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EPISODE = "episode"
    SKILL = "skill"

@dataclass
class Memory:
    id: str
    content: str
    embedding: List[float]
    agent_id: str
    session_id: Optional[str]
    memory_type: MemoryType
    tier: MemoryTier
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 1
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['memory_type'] = self.memory_type.value
        d['tier'] = self.tier.value
        d['created_at'] = self.created_at.isoformat()
        d['last_accessed'] = self.last_accessed.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Memory':
        d['memory_type'] = MemoryType(d['memory_type'])
        d['tier'] = MemoryTier(d['tier'])
        d['created_at'] = datetime.fromisoformat(d['created_at'])
        d['last_accessed'] = datetime.fromisoformat(d['last_accessed'])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

class SimpleEmbedding:
    def __init__(self, dim: int = 128):
        self.dim = dim
    
    def _vector(self, seed: str) -> List[float]:
        h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        random.seed(h)
        vec = [random.gauss(0, 1) for _ in range(self.dim)]
        norm = math.sqrt(sum(x*x for x in vec))
        return [x/norm for x in vec] if norm > 0 else vec
    
    def embed(self, text: str) -> List[float]:
        tokens = text.lower().split()
        if not tokens:
            return [0.0] * self.dim
        from collections import Counter
        tf = Counter(tokens)
        emb = [0.0] * self.dim
        for tok, cnt in tf.items():
            v = self._vector(tok)
            for i in range(self.dim):
                emb[i] += cnt * v[i]
        norm = math.sqrt(sum(x*x for x in emb))
        return [x/norm for x in emb] if norm > 0 else emb

def cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na>0 and nb>0 else 0.0

class MemoryStore:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.dir = MEMORY_DIR / agent_id
        self.dir.mkdir(exist_ok=True)
        self.embedder = SimpleEmbedding(128)
        self.memories: Dict[str, Memory] = {}
        self._load()
    
    def _load(self):
        for f in self.dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    mem = Memory.from_dict(data)
                    self.memories[mem.id] = mem
            except Exception as e:
                print(f"Failed to load {f}: {e}")
    
    def _save(self, m: Memory):
        with open(self.dir/f"{m.id}.json", 'w') as fp:
            json.dump(m.to_dict(), fp)
    
    def store(self, content: str, mtype: MemoryType = MemoryType.EPISODE,
              tier: MemoryTier = MemoryTier.EPISODIC, importance: float = 0.5,
              session_id: Optional[str] = None, tags: List[str] = None) -> Memory:
        mid = hashlib.sha256(f"{self.agent_id}:{content}:{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        m = Memory(id=mid, content=content, embedding=self.embedder.embed(content),
                   agent_id=self.agent_id, session_id=session_id, memory_type=mtype,
                   tier=tier, importance=importance, tags=tags or [])
        self.memories[mid] = m
        self._save(m)
        return m
    
    def query(self, q: str, tiers: List[MemoryTier] = None, k: int = 5,
              session_id: Optional[str] = None) -> List[Tuple[Memory, float]]:
        qemb = self.embedder.embed(q)
        tiers = tiers or [MemoryTier.SEMANTIC, MemoryTier.EPISODIC]
        scored = []
        for m in self.memories.values():
            if m.tier not in tiers: continue
            sim = cosine_sim(qemb, m.embedding)
            if sim < 0.3: continue
            hours = (datetime.now() - m.created_at).total_seconds() / 3600
            recency = max(0, 1 - hours/168) * 0.2
            sess = 0.1 if session_id and m.session_id == session_id else 0
            access = min(m.access_count/10, 0.1)
            score = sim*0.5 + recency + sess + access + m.importance*0.2
            scored.append((m, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        for m,_ in scored[:k]:
            m.last_accessed = datetime.now()
            m.access_count += 1
            self._save(m)
        return scored[:k]
    
    def stats(self) -> Dict:
        return {"total": len(self.memories), "tiers": {t.value: sum(1 for m in self.memories.values() if m.tier==t) for t in MemoryTier}}

class OpenClawMemory:
    def __init__(self, agent_id: str = "kimi-claw"):
        self.store = MemoryStore(agent_id)
    
    def remember(self, content: str, memory_type: str = "fact", importance: float = 0.5, permanent: bool = False, tags: List[str] = None) -> str:
        m = self.store.store(content, MemoryType(memory_type), MemoryTier.SEMANTIC if permanent else MemoryTier.EPISODIC, importance, tags=tags)
        return m.id
    
    def recall(self, query: str, k: int = 5) -> List[str]:
        return [m.content for m,_ in self.store.query(query, k=k)]
    
    def context_for_prompt(self, query: str, max_tokens: int = 1000) -> str:
        results = self.store.query(query, k=15)
        facts, prefs, eps = [], [], []
        tokens = 0
        for m,_ in results:
            t = len(m.content.split())
            if tokens + t > max_tokens: break
            if m.memory_type == MemoryType.FACT: facts.append(m.content)
            elif m.memory_type == MemoryType.PREFERENCE: prefs.append(m.content)
            elif m.memory_type == MemoryType.EPISODE: eps.append(m.content)
            tokens += t
        sections = []
        if facts: sections.append("## Facts\n" + "\n".join(f"- {f}" for f in facts[:5]))
        if prefs: sections.append("## Preferences\n" + "\n".join(f"- {p}" for p in prefs[:3]))
        if eps: sections.append("## Recent\n" + "\n".join(f"- {e}" for e in eps[:3]))
        return "\n\n".join(sections)

if __name__ == "__main__":
    print("OpenClaw Memory System - Demo")
    mem = OpenClawMemory("demo")
    mem.remember("User runs Proxmox infrastructure", "fact", 0.9, True)
    mem.remember("User prefers direct communication", "preference", 0.95, True)
    mem.remember("Debugged Docker yesterday", "episode", 0.6)
    print(f"\nStored: {mem.store.stats()}")
    print(f"\nQuery 'communication': {mem.recall('communication style', k=2)}")
    print(f"\nContext:\n{mem.context_for_prompt('how to respond')}")
    print(f"\nData saved to: {MEMORY_DIR}")