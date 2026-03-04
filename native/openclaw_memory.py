#!/usr/bin/env python3
"""
OpenClaw Memory System - Native Implementation
Fully compatible with OpenClaw's memory conventions.

Integrates with:
- MEMORY.md (long-term curated memory)
- memory/YYYY-MM-DD.md (daily logs)
- memory_search tool semantics
- memory_get tool semantics

Multi-provider embeddings: Ollama → HuggingFace → OpenAI → Hash fallback
"""
import json
import hashlib
import math
import os
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Iterator
from dataclasses import dataclass, field, asdict
from enum import Enum

# Add native directory to path for imports
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

# Try to import multi-provider embeddings
try:
    from embeddings import MultiProviderEmbedding, get_embedder
    HAS_ML_EMBEDDINGS = True
except ImportError:
    HAS_ML_EMBEDDINGS = False

# Import security patch for path traversal protection
try:
    from security_patch import PathSecurity, ValidationError
except ImportError:
    # Fallback if security_patch not available
    class ValidationError(Exception):
        pass
    
    class PathSecurity:
        @staticmethod
        def safe_path(base_dir: Path, *parts: str) -> Path:
            """Safely construct a path within base_dir."""
            base_dir = base_dir.resolve()
            target = base_dir.joinpath(*parts)
            target = target.resolve()
            try:
                target.relative_to(base_dir)
            except ValueError:
                raise ValidationError(f"Path traversal detected")
            return target
        
        @staticmethod
        def safe_filename(filename: str) -> str:
            """Sanitize a filename."""
            filename = filename.replace('/', '_').replace('\\', '_')
            filename = filename.replace('\x00', '')
            filename = filename.lstrip('.')
            if len(filename) > 255:
                filename = filename[:255]
            if not filename:
                filename = 'unnamed'
            return filename

# OpenClaw workspace integration - use environment variable or default to user home
WORKSPACE_DIR = Path(os.getenv("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))

# Use PathSecurity to ensure we stay within workspace
MEMORY_DIR = PathSecurity.safe_path(WORKSPACE_DIR, "memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Long-term memory file
MEMORY_MD = WORKSPACE_DIR / "MEMORY.md"


class MemoryTier(Enum):
    WORKING = "working"      # Current session context
    EPISODIC = "episodic"    # Daily logs
    SEMANTIC = "semantic"    # MEMORY.md curated facts


class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EPISODE = "episode"
    SKILL = "skill"
    DECISION = "decision"


@dataclass
class MemoryChunk:
    """A chunk of memory with metadata - compatible with OpenClaw memory_search results"""
    id: str
    content: str
    embedding: List[float]
    source_path: str           # File path (e.g., "memory/2026-03-03.md" or "MEMORY.md")
    start_line: int            # Line number in source file
    end_line: int
    memory_type: Optional[MemoryType] = None
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    score: float = 0.0         # Search relevance score

    def to_search_result(self) -> Dict[str, Any]:
        """Format as OpenClaw memory_search result"""
        return {
            "text": self.content,
            "path": self.source_path,
            "lines": f"{self.start_line}-{self.end_line}",
            "score": round(self.score, 4),
            "source": f"{self.source_path}#L{self.start_line}-L{self.end_line}"
        }


class SimpleEmbedding:
    """Fallback: lightweight hash-based embeddings (no ML)"""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        """Create embedding from text using hash-based random projections"""
        tokens = text.lower().split()
        if not tokens:
            return [0.0] * self.dim

        from collections import Counter
        tf = Counter(tokens)

        embedding = [0.0] * self.dim
        for token, count in tf.items():
            # Hash-based projection
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            random.seed(h)
            proj = [random.gauss(0, 1) for _ in range(self.dim)]
            norm = math.sqrt(sum(x*x for x in proj))
            if norm > 0:
                proj = [x/norm for x in proj]

            for i in range(self.dim):
                embedding[i] += count * proj[i]

        norm = math.sqrt(sum(x*x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding


class EmbeddingAdapter:
    """Adapter that uses multi-provider embeddings if available, else fallback"""

    def __init__(self, preferred: Optional[str] = None):
        self._embedder = None
        self._fallback = SimpleEmbedding(dim=384)

        if HAS_ML_EMBEDDINGS:
            try:
                self._embedder = get_embedder(preferred)
                print(f"[Memory] Using embedding provider: {self._embedder.active_provider.name if self._embedder.active_provider else 'hash-fallback'}")
            except Exception as e:
                print(f"[Memory] ML embeddings failed, using fallback: {e}")

    @property
    def dim(self) -> int:
        if self._embedder:
            return self._embedder.dim
        return self._fallback.dim

    def embed(self, text: str) -> List[float]:
        if self._embedder:
            try:
                return self._embedder.embed(text)
            except Exception as e:
                print(f"[Memory] Embedding failed, using fallback: {e}")
        return self._fallback.embed(text)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors"""
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity for MMR diversity scoring"""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


class OpenClawMemoryStore:
    """
    OpenClaw-compatible memory store.

    Follows OpenClaw conventions:
    - MEMORY.md for curated long-term memory
    - memory/YYYY-MM-DD.md for daily episodic logs
    - Chunking with ~400 token target, 80 token overlap
    - Hybrid search: vector + BM25-style keyword matching
    - MMR for diversity, temporal decay for recency
    """

    def __init__(self, agent_id: str = "default", embedding_provider: Optional[str] = None):
        self.agent_id = agent_id
        self.embedder = EmbeddingAdapter(preferred=embedding_provider)
        self.chunks: Dict[str, MemoryChunk] = {}
        self.index: Dict[str, List[str]] = {}  # token -> chunk_ids (simple inverted index)

        # Config
        self.chunk_size = 400  # words
        self.chunk_overlap = 80  # words
        self.vector_weight = 0.7
        self.text_weight = 0.3

        # Load existing memory files
        self._load_memory_md()
        self._load_daily_logs()

    def _get_daily_path(self, date: Optional[datetime] = None) -> Path:
        """Get path for daily memory file using safe path construction"""
        date = date or datetime.now()
        filename = f"{date.strftime('%Y-%m-%d')}.md"
        # Use safe_filename to prevent path traversal in date
        safe_filename = PathSecurity.safe_filename(filename)
        return MEMORY_DIR / safe_filename

    def _chunk_text(self, text: str, source_path: str,
                   base_line: int = 1) -> Iterator[Tuple[str, int, int]]:
        """
        Split text into overlapping chunks.
        Returns (chunk_text, start_line, end_line).
        """
        lines = text.split('\n')
        words = []
        line_map = []  # word index -> line number

        for line_num, line in enumerate(lines, 1):
            line_words = line.split()
            for _ in line_words:
                line_map.append(line_num)
            words.extend(line_words)

        if not words:
            return

        # Create overlapping chunks
        start = 0
        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk_words = words[start:end]
            chunk_text = ' '.join(chunk_words)

            start_line = line_map[start] if start < len(line_map) else base_line
            end_line = line_map[min(end - 1, len(line_map) - 1)] if line_map else base_line

            yield chunk_text, start_line, end_line

            # Move forward with overlap
            start += self.chunk_size - self.chunk_overlap
            if start >= len(words):
                break

    def _index_chunk(self, chunk: MemoryChunk):
        """Add chunk to inverted index for keyword search"""
        tokens = set(chunk.content.lower().split())
        for token in tokens:
            if token not in self.index:
                self.index[token] = []
            self.index[token].append(chunk.id)

    def _load_memory_md(self):
        """Load and index MEMORY.md"""
        if not MEMORY_MD.exists():
            return

        text = MEMORY_MD.read_text()
        self._index_file(text, "MEMORY.md")

    def _load_daily_logs(self, days_back: int = 7):
        """Load recent daily memory files"""
        for i in range(days_back):
            date = datetime.now() - timedelta(days=i)
            path = self._get_daily_path(date)
            if path.exists():
                text = path.read_text()
                self._index_file(text, f"memory/{date.strftime('%Y-%m-%d')}.md")

    def _index_file(self, text: str, source_path: str):
        """Index a memory file into chunks"""
        for chunk_text, start_line, end_line in self._chunk_text(text, source_path):
            chunk_id = hashlib.sha256(
                f"{source_path}:{start_line}:{chunk_text[:50]}".encode()
            ).hexdigest()[:16]

            if chunk_id in self.chunks:
                continue

            embedding = self.embedder.embed(chunk_text)

            chunk = MemoryChunk(
                id=chunk_id,
                content=chunk_text,
                embedding=embedding,
                source_path=source_path,
                start_line=start_line,
                end_line=end_line
            )

            self.chunks[chunk_id] = chunk
            self._index_chunk(chunk)

    def _bm25_score(self, query: str, chunk: MemoryChunk) -> float:
        """Simple BM25-inspired scoring"""
        query_tokens = set(query.lower().split())
        chunk_tokens = set(chunk.content.lower().split())

        if not query_tokens:
            return 0.0

        matches = len(query_tokens & chunk_tokens)
        return matches / len(query_tokens)

    def _temporal_decay(self, chunk: MemoryChunk, half_life_days: float = 30.0) -> float:
        """Apply temporal decay to score based on file age"""
        # Parse date from daily log filename
        match = re.search(r'(\d{4}-\d{2}-\d{2})', chunk.source_path)
        if match:
            try:
                file_date = datetime.strptime(match.group(1), '%Y-%m-%d')
            except:
                file_date = chunk.created_at
        else:
            # MEMORY.md doesn't decay
            if chunk.source_path == "MEMORY.md":
                return 1.0
            file_date = chunk.created_at

        age_days = (datetime.now() - file_date).total_seconds() / 86400
        lambda_decay = math.log(2) / half_life_days
        return math.exp(-lambda_decay * age_days)

    def search(self,
               query: str,
               k: int = 6,
               hybrid: bool = True,
               mmr: bool = False,
               mmr_lambda: float = 0.7,
               temporal_decay: bool = False,
               half_life_days: float = 30.0) -> List[MemoryChunk]:
        """
        Search memory with OpenClaw-compatible semantics.

        Args:
            query: Search query
            k: Number of results to return
            hybrid: Use hybrid vector + keyword search
            mmr: Use Maximal Marginal Relevance for diversity
            mmr_lambda: Balance between relevance (1.0) and diversity (0.0)
            temporal_decay: Apply recency boosting
            half_life_days: Days for score to halve with temporal decay
        """
        query_emb = self.embedder.embed(query)

        # Vector search
        vector_scores = {}
        for chunk_id, chunk in self.chunks.items():
            sim = cosine_similarity(query_emb, chunk.embedding)
            vector_scores[chunk_id] = sim

        # Hybrid scoring
        if hybrid:
            scores = {}
            for chunk_id, chunk in self.chunks.items():
                v_score = vector_scores.get(chunk_id, 0)
                t_score = self._bm25_score(query, chunk)
                # Normalize weights
                total_weight = self.vector_weight + self.text_weight
                vw = self.vector_weight / total_weight
                tw = self.text_weight / total_weight
                scores[chunk_id] = vw * v_score + tw * t_score
        else:
            scores = vector_scores

        # Apply temporal decay
        if temporal_decay:
            for chunk_id in scores:
                decay = self._temporal_decay(self.chunks[chunk_id], half_life_days)
                scores[chunk_id] *= decay

        # Get candidate pool
        candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        candidates = candidates[:k * 4]  # Top 4x for MMR reranking

        # MMR reranking for diversity
        if mmr and len(candidates) > k:
            selected = []
            remaining = list(candidates)

            while len(selected) < k and remaining:
                best_score = -1
                best_idx = 0

                for i, (chunk_id, relevance) in enumerate(remaining):
                    # Compute max similarity to already selected
                    max_sim = 0
                    for sel_id, _ in selected:
                        sim = jaccard_similarity(
                            self.chunks[chunk_id].content,
                            self.chunks[sel_id].content
                        )
                        max_sim = max(max_sim, sim)

                    # MMR score
                    mmr_score = mmr_lambda * relevance - (1 - mmr_lambda) * max_sim

                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = i

                selected.append(remaining.pop(best_idx))

            candidates = selected
        else:
            candidates = candidates[:k]

        # Build results
        results = []
        for chunk_id, score in candidates:
            chunk = self.chunks[chunk_id]
            chunk.score = score
            chunk.last_accessed = datetime.now()
            chunk.access_count += 1
            results.append(chunk)

        return results

    def get(self, path: str, start_line: Optional[int] = None,
            lines: Optional[int] = None) -> str:
        """
        Get memory content by path - compatible with OpenClaw memory_get.

        Args:
            path: File path (e.g., "MEMORY.md" or "memory/2026-03-03.md")
            start_line: Starting line number (1-indexed)
            lines: Number of lines to read
        """
        # Resolve path with path traversal protection
        if path == "MEMORY.md":
            file_path = MEMORY_MD
        elif path.startswith("memory/"):
            # Extract the filename and validate it
            filename = path[7:]  # Remove "memory/" prefix
            safe_filename = PathSecurity.safe_filename(filename)
            file_path = WORKSPACE_DIR / "memory" / safe_filename
        else:
            # Try as workspace-relative with path traversal protection
            safe_path = PathSecurity.safe_filename(path)
            file_path = WORKSPACE_DIR / safe_path

        # Final safety check - ensure file is within workspace
        try:
            file_path.resolve().relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise ValidationError(f"Path traversal detected: {path}")

        if not file_path.exists():
            return ""

        content = file_path.read_text()

        if start_line is None:
            return content

        # Extract specific lines
        all_lines = content.split('\n')
        start_idx = max(0, start_line - 1)
        end_idx = len(all_lines)
        if lines is not None:
            end_idx = min(start_idx + lines, len(all_lines))

        return '\n'.join(all_lines[start_idx:end_idx])

    def write_memory_md(self, content: str, append: bool = True):
        """Write to MEMORY.md (curated long-term memory)"""
        # Ensure MEMORY.md is within workspace
        try:
            MEMORY_MD.resolve().relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise ValidationError("MEMORY.md path is outside workspace")

        if append and MEMORY_MD.exists():
            existing = MEMORY_MD.read_text()
            if existing and not existing.endswith('\n'):
                existing += '\n'
            content = existing + content

        MEMORY_MD.write_text(content)

        # Re-index
        self.chunks.clear()
        self.index.clear()
        self._load_memory_md()
        self._load_daily_logs()

    def write_daily_log(self, content: str, date: Optional[datetime] = None):
        """Write to daily memory file with path safety"""
        path = self._get_daily_path(date)
        
        # Ensure path is within MEMORY_DIR
        try:
            path.resolve().relative_to(MEMORY_DIR.resolve())
        except ValueError:
            raise ValidationError(f"Daily log path is outside memory directory")

        if path.exists():
            existing = path.read_text()
            if existing and not existing.endswith('\n'):
                existing += '\n'
            content = existing + content
        else:
            # Add date header for new files
            date_str = (date or datetime.now()).strftime('%Y-%m-%d')
            content = f"# {date_str}\n\n{content}"

        path.write_text(content)

        # Re-index this file
        self._index_file(content, f"memory/{(date or datetime.now()).strftime('%Y-%m-%d')}.md")

    def stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            "total_chunks": len(self.chunks),
            "files_indexed": len(set(c.source_path for c in self.chunks.values())),
            "memory_md_exists": MEMORY_MD.exists(),
            "daily_logs_count": len(list(MEMORY_DIR.glob("*.md")))
        }


# OpenClaw Tool Interface
class MemoryTools:
    """
    OpenClaw-compatible memory tool interface.
    Drop-in replacement for OpenClaw's memory_search and memory_get.
    """

    def __init__(self, agent_id: str = "default"):
        self.store = OpenClawMemoryStore(agent_id)

    def memory_search(self,
                      query: str,
                      k: int = 6,
                      hybrid: bool = True,
                      mmr: bool = False,
                      temporal_decay: bool = False) -> str:
        """
        Search memory - compatible with OpenClaw memory_search tool.
        Returns JSON string of results.
        """
        results = self.store.search(
            query=query,
            k=k,
            hybrid=hybrid,
            mmr=mmr,
            temporal_decay=temporal_decay
        )

        output = []
        for chunk in results:
            result = chunk.to_search_result()
            # Add citation footer if enabled
            result["text"] += f"\n\nSource: {result['source']}"
            output.append(result)

        return json.dumps(output, indent=2)

    def memory_get(self, path: str, from_line: Optional[int] = None,
                   lines: Optional[int] = None) -> str:
        """
        Get memory content - compatible with OpenClaw memory_get tool.
        """
        content = self.store.get(path, from_line, lines)
        return json.dumps({"text": content, "path": path}, indent=2)

    def memory_write(self, content: str, to: str = "daily",
                     permanent: bool = False) -> str:
        """
        Write memory (extension - not in core OpenClaw tools).

        Args:
            content: Content to write
            to: "daily" or "memory"
            permanent: If True, writes to MEMORY.md instead of daily log
        """
        if permanent or to == "memory":
            self.store.write_memory_md(content)
            return f"Written to MEMORY.md"
        else:
            self.store.write_daily_log(content)
            return f"Written to daily log"

    # Convenience methods for agent use
    def remember(self, content: str, memory_type: str = "fact",
                 importance: float = 0.5, permanent: bool = False,
                 tags: List[str] = None) -> str:
        """Store a memory with metadata tagging"""
        # Add type prefix to content for categorization
        if memory_type and not content.lower().startswith(memory_type.lower()):
            content = f"[{memory_type.upper()}] {content}"

        # Add importance indicator for high-importance memories
        if importance >= 0.8 and permanent:
            content = f"⭐ {content}"

        result = self.memory_write(content, permanent=permanent)

        # Store tags in a separate metadata file if provided
        if tags:
            self._store_tags(content, tags)

        return result

    def _store_tags(self, content: str, tags: List[str]):
        """Store tags for a memory entry with path safety"""
        tags_file = WORKSPACE_DIR / ".memory_tags.json"
        
        # Ensure tags file is within workspace
        try:
            tags_file.resolve().relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise ValidationError("Tags file path is outside workspace")

        # Load existing tags
        existing = {}
        if tags_file.exists():
            try:
                with open(tags_file) as f:
                    existing = json.load(f)
            except:
                pass

        # Create hash of content for key
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        existing[content_hash] = {
            "content_preview": content[:100],
            "tags": tags,
            "timestamp": datetime.now().isoformat()
        }

        # Save
        with open(tags_file, 'w') as f:
            json.dump(existing, f, indent=2)

    def recall(self, query: str, k: int = 5) -> List[str]:
        """Retrieve memories as list of content strings"""
        results = self.store.search(query, k=k)
        return [chunk.content for chunk in results]

    def context_for_prompt(self, query: str, max_tokens: int = 1500) -> str:
        """Generate formatted context for LLM prompts"""
        results = self.store.search(query, k=15)

        # Organize by source
        facts = []
        prefs = []
        episodes = []

        tokens = 0
        for chunk in results:
            t = len(chunk.content.split())
            if tokens + t > max_tokens:
                break

            # Categorize based on source
            if chunk.source_path == "MEMORY.md":
                facts.append(chunk.content)
            elif "preference" in chunk.content.lower():
                prefs.append(chunk.content)
            else:
                episodes.append(chunk.content)

            tokens += t

        sections = []
        if facts:
            sections.append("## Facts\n" + "\n".join(f"- {f}" for f in facts[:5]))
        if prefs:
            sections.append("## Preferences\n" + "\n".join(f"- {p}" for p in prefs[:3]))
        if episodes:
            sections.append("## Recent\n" + "\n".join(f"- {e}" for e in episodes[:3]))

        return "\n\n".join(sections)


# Demo
if __name__ == "__main__":
    print("OpenClaw Memory System - Demo")
    print("=" * 60)

    tools = MemoryTools("demo")

    # Write some memories
    print("\n1. Writing memories...")
    tools.memory_write("User runs Proxmox infrastructure at home lab", permanent=True)
    tools.memory_write("User prefers direct technical communication without corporate fluff", permanent=True)
    tools.memory_write("Debugged Docker networking issue - container couldn't reach host", to="daily")
    tools.memory_write("Learned about OpenClaw memory system architecture today", to="daily")

    print(f"   Stats: {tools.store.stats()}")

    # Search
    print("\n2. Searching for 'communication preferences'...")
    results = tools.memory_search("communication preferences", k=3)
    print(results)

    print("\n3. Searching with MMR diversity...")
    results = tools.memory_search("technical setup", k=3, mmr=True)
    print(results)

    # Get specific file
    print("\n4. Getting MEMORY.md content...")
    content = tools.memory_get("MEMORY.md")
    print(content[:500] if len(content) > 500 else content)

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"Memory files location: {WORKSPACE_DIR}")
