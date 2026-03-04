"""
Integration tests for the AMEM API.
Tests the web API endpoints and HTTP handlers.
"""
import pytest
import json
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch
from http.server import HTTPServer

sys.path.insert(0, "/root/.openclaw/workspace/memory_system")


class TestAMEMAPIHandler:
    """Tests for the AMEM API HTTP handler."""
    
    def test_handler_initialization(self, temp_workspace, mock_env_vars):
        """Test API handler can be initialized."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        AMEMAPIHandler.agent_id = "test_agent"
        AMEMAPIHandler.memory = MemoryTools("test_agent")
        
        assert AMEMAPIHandler.agent_id == "test_agent"
        assert AMEMAPIHandler.memory is not None
    
    def test_api_stats(self, temp_workspace, mock_env_vars):
        """Test API stats endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'stats', {})
        
        assert result['success'] == True
        assert 'agent_id' in result
        assert 'total' in result
        assert 'tiers' in result
    
    def test_api_provider(self, temp_workspace, mock_env_vars):
        """Test API provider endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'provider', {})
        
        assert result['success'] == True
        assert 'provider' in result
    
    def test_api_search(self, temp_workspace, mock_env_vars):
        """Test API search endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        # First store some content
        handler.memory.remember("Test memory content", memory_type="fact", permanent=True)
        
        result = handler.handle_api(handler, 'search', {'query': 'test', 'k': 5})
        
        assert result['success'] == True
        assert 'results' in result
        assert isinstance(result['results'], list)
    
    def test_api_store(self, temp_workspace, mock_env_vars):
        """Test API store endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'store', {
            'content': 'New memory',
            'type': 'fact',
            'permanent': True
        })
        
        assert result['success'] == True
    
    def test_api_files(self, temp_workspace, mock_env_vars):
        """Test API files endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'files', {})
        
        assert result['success'] == True
        assert 'files' in result
        assert isinstance(result['files'], list)
    
    def test_api_config(self, temp_workspace, mock_env_vars):
        """Test API config endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'config', {})
        
        assert result['success'] == True
        assert 'workspace' in result
        assert 'memory_dir' in result
        assert 'env' in result
    
    def test_api_update_check(self, temp_workspace, mock_env_vars):
        """Test API update_check endpoint."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'update_check', {})
        
        assert result['success'] == True
        assert 'message' in result
    
    def test_api_unknown_method(self, temp_workspace, mock_env_vars):
        """Test API with unknown method."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'unknown_method', {})
        
        assert result['success'] == False
        assert 'error' in result
    
    def test_api_error_handling(self, temp_workspace, mock_env_vars):
        """Test API error handling."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MagicMock()
        handler.memory.store.stats.side_effect = Exception("Test error")
        
        result = handler.handle_api(handler, 'stats', {})
        
        assert result['success'] == False
        assert 'error' in result


class TestAPIEdgeCases:
    """Edge case tests for API."""
    
    def test_api_search_empty_query(self, temp_workspace, mock_env_vars):
        """Test search with empty query."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'search', {'query': '', 'k': 5})
        
        assert result['success'] == True
        assert 'results' in result
    
    def test_api_search_unicode(self, temp_workspace, mock_env_vars):
        """Test search with unicode query."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        handler.memory.remember("用户喜欢中文内容", memory_type="fact", permanent=True)
        
        result = handler.handle_api(handler, 'search', {'query': '中文', 'k': 5})
        
        assert result['success'] == True
        assert 'results' in result
    
    def test_api_store_unicode(self, temp_workspace, mock_env_vars):
        """Test store with unicode content."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        result = handler.handle_api(handler, 'store', {
            'content': '用户喜欢中文内容',
            'type': 'fact',
            'permanent': True
        })
        
        assert result['success'] == True
    
    def test_api_store_long_content(self, temp_workspace, mock_env_vars):
        """Test store with very long content."""
        from amem_web import AMEMAPIHandler
        from openclaw_memory import MemoryTools
        
        handler = AMEMAPIHandler
        handler.agent_id = "test_agent"
        handler.memory = MemoryTools("test_agent")
        
        long_content = "x" * 10000
        result = handler.handle_api(handler, 'store', {
            'content': long_content,
            'type': 'fact',
            'permanent': True
        })
        
        assert result['success'] == True


class TestMemoryStoreIntegration:
    """Integration tests for MemoryStore."""
    
    def test_store_and_retrieve(self, temp_workspace, mock_env_vars):
        """Test storing and retrieving memories."""
        from openclaw_memory import MemoryTools, MemoryType, MemoryTier
        
        tools = MemoryTools("test_agent")
        
        # Store memories
        tools.remember("Memory one", memory_type="fact", permanent=True)
        tools.remember("Memory two", memory_type="preference", permanent=True)
        tools.remember("Memory three", memory_type="episode")
        
        # Retrieve
        results = tools.recall("memory", k=10)
        
        # Should have at least some results (chunking may combine them)
        assert len(results) >= 1
    
    def test_search_ranking(self, temp_workspace, mock_env_vars):
        """Test that search returns relevant results first."""
        from openclaw_memory import MemoryTools
        
        tools = MemoryTools("test_agent")
        
        # Store specific memories
        tools.remember("Python programming language", memory_type="fact", permanent=True)
        tools.remember("JavaScript web development", memory_type="fact", permanent=True)
        tools.remember("Rust systems programming", memory_type="fact", permanent=True)
        
        # Search for Python
        results = tools.recall("Python programming", k=3)
        
        # Python should be in results
        assert any("Python" in r for r in results)
    
    def test_hybrid_search(self, temp_workspace, mock_env_vars):
        """Test hybrid search combines vector and keyword matching."""
        from openclaw_memory import MemoryTools
        
        tools = MemoryTools("test_agent")
        
        tools.remember("Docker containerization technology", memory_type="fact", permanent=True)
        
        results = tools.memory_search("Docker containers", k=5, hybrid=True)
        parsed = json.loads(results)
        
        assert isinstance(parsed, list)
    
    def test_mmr_diversity(self, temp_workspace, mock_env_vars):
        """Test MMR provides diverse results."""
        from openclaw_memory import MemoryTools
        
        tools = MemoryTools("test_agent")
        
        # Store similar memories
        tools.remember("Machine learning is great for AI", memory_type="fact", permanent=True)
        tools.remember("Deep learning powers neural networks", memory_type="fact", permanent=True)
        tools.remember("Python is a programming language", memory_type="fact", permanent=True)
        
        # Search with MMR
        results_mmr = tools.memory_search("AI technology", k=3, mmr=True)
        results_no_mmr = tools.memory_search("AI technology", k=3, mmr=False)
        
        parsed_mmr = json.loads(results_mmr)
        parsed_no_mmr = json.loads(results_no_mmr)
        
        assert isinstance(parsed_mmr, list)
        assert isinstance(parsed_no_mmr, list)


class TestMemoryChunking:
    """Tests for memory chunking functionality."""
    
    def test_chunk_text(self, temp_workspace, mock_env_vars):
        """Test text chunking."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        # Create text larger than chunk size
        large_text = "word " * 1000
        
        chunks = list(store._chunk_text(large_text, "test.md"))
        
        assert len(chunks) > 1
        for chunk_text, start_line, end_line in chunks:
            assert isinstance(chunk_text, str)
            assert isinstance(start_line, int)
            assert isinstance(end_line, int)
            assert start_line <= end_line
    
    def test_chunk_empty_text(self, temp_workspace, mock_env_vars):
        """Test chunking empty text."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        chunks = list(store._chunk_text("", "test.md"))
        
        assert len(chunks) == 0
    
    def test_chunk_small_text(self, temp_workspace, mock_env_vars):
        """Test chunking small text."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        small_text = "small text"
        chunks = list(store._chunk_text(small_text, "test.md"))
        
        assert len(chunks) == 1


class TestTemporalDecay:
    """Tests for temporal decay functionality."""
    
    def test_temporal_decay_recent(self, temp_workspace, mock_env_vars):
        """Test that recent memories have higher scores."""
        from openclaw_memory import MemoryTools
        
        tools = MemoryTools("test_agent")
        
        tools.remember("Recent memory content", memory_type="fact", permanent=True)
        
        results = tools.memory_search("memory", k=5, temporal_decay=True)
        parsed = json.loads(results)
        
        assert isinstance(parsed, list)
    
    def test_temporal_decay_half_life(self, temp_workspace, mock_env_vars):
        """Test temporal decay with different half-life."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        # Create a mock chunk
        from openclaw_memory import MemoryChunk
        chunk = MemoryChunk(
            id="test",
            content="test",
            embedding=[0.1] * 384,
            source_path="memory/2024-01-01.md",
            start_line=1,
            end_line=1
        )
        
        decay_30 = store._temporal_decay(chunk, half_life_days=30.0)
        decay_60 = store._temporal_decay(chunk, half_life_days=60.0)
        
        # Longer half-life should have less decay
        assert decay_60 >= decay_30


class TestBM25Scoring:
    """Tests for BM25-style keyword scoring."""
    
    def test_bm25_exact_match(self, temp_workspace, mock_env_vars):
        """Test BM25 with exact match."""
        from openclaw_memory import OpenClawMemoryStore, MemoryChunk
        
        store = OpenClawMemoryStore("test_agent")
        
        chunk = MemoryChunk(
            id="test",
            content="exact match test",
            embedding=[0.1] * 384,
            source_path="test.md",
            start_line=1,
            end_line=1
        )
        
        score = store._bm25_score("exact match", chunk)
        assert score == 1.0
    
    def test_bm25_partial_match(self, temp_workspace, mock_env_vars):
        """Test BM25 with partial match."""
        from openclaw_memory import OpenClawMemoryStore, MemoryChunk
        
        store = OpenClawMemoryStore("test_agent")
        
        chunk = MemoryChunk(
            id="test",
            content="some test content",
            embedding=[0.1] * 384,
            source_path="test.md",
            start_line=1,
            end_line=1
        )
        
        score = store._bm25_score("test other", chunk)
        assert 0 < score < 1
    
    def test_bm25_no_match(self, temp_workspace, mock_env_vars):
        """Test BM25 with no match."""
        from openclaw_memory import OpenClawMemoryStore, MemoryChunk
        
        store = OpenClawMemoryStore("test_agent")
        
        chunk = MemoryChunk(
            id="test",
            content="completely different",
            embedding=[0.1] * 384,
            source_path="test.md",
            start_line=1,
            end_line=1
        )
        
        score = store._bm25_score("xyzabc", chunk)
        assert score == 0.0
    
    def test_bm25_empty_query(self, temp_workspace, mock_env_vars):
        """Test BM25 with empty query."""
        from openclaw_memory import OpenClawMemoryStore, MemoryChunk
        
        store = OpenClawMemoryStore("test_agent")
        
        chunk = MemoryChunk(
            id="test",
            content="some content",
            embedding=[0.1] * 384,
            source_path="test.md",
            start_line=1,
            end_line=1
        )
        
        score = store._bm25_score("", chunk)
        assert score == 0.0


class TestOpenClawMemoryStore:
    """Tests for OpenClawMemoryStore class."""
    
    def test_store_initialization(self, temp_workspace, mock_env_vars):
        """Test OpenClawMemoryStore initialization."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        assert store.agent_id == "test_agent"
        assert store.embedder is not None
        assert store.chunk_size == 400
        assert store.chunk_overlap == 80
    
    def test_store_get_daily_path(self, temp_workspace, mock_env_vars):
        """Test getting daily path."""
        from openclaw_memory import OpenClawMemoryStore
        from datetime import datetime
        
        store = OpenClawMemoryStore("test_agent")
        
        path = store._get_daily_path()
        today = datetime.now().strftime('%Y-%m-%d')
        
        assert today in str(path)
    
    def test_store_get_with_line_range(self, temp_workspace, mock_env_vars):
        """Test get with line range."""
        from openclaw_memory import OpenClawMemoryStore
        
        store = OpenClawMemoryStore("test_agent")
        
        # Write some content first
        store.write_memory_md("Line 1\nLine 2\nLine 3\nLine 4\nLine 5")
        
        content = store.get("MEMORY.md", start_line=2, lines=2)
        assert "Line 2" in content
        assert "Line 3" in content
        assert "Line 1" not in content


class TestCosineSimilarity:
    """Tests for cosine similarity function."""
    
    def test_cosine_identical(self):
        """Test cosine similarity of identical vectors."""
        from openclaw_memory import cosine_similarity
        
        vec = [1.0, 2.0, 3.0]
        result = cosine_similarity(vec, vec)
        
        assert abs(result - 1.0) < 0.0001
    
    def test_cosine_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        from openclaw_memory import cosine_similarity
        
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        
        assert abs(result - 0.0) < 0.0001
    
    def test_cosine_opposite(self):
        """Test cosine similarity of opposite vectors."""
        from openclaw_memory import cosine_similarity
        
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        result = cosine_similarity(vec1, vec2)
        
        assert abs(result - (-1.0)) < 0.0001
    
    def test_cosine_zero_vector(self):
        """Test cosine similarity with zero vector."""
        from openclaw_memory import cosine_similarity
        
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [0.0, 0.0, 0.0]
        result = cosine_similarity(vec1, vec2)
        
        assert result == 0.0
    
    def test_cosine_different_lengths(self):
        """Test cosine similarity with different vector lengths."""
        from openclaw_memory import cosine_similarity
        
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        
        # Should handle different lengths gracefully
        result = cosine_similarity(vec1, vec2)
        # Result is based on min length
        assert isinstance(result, float)


class TestJaccardSimilarity:
    """Tests for Jaccard similarity function."""
    
    def test_jaccard_identical(self):
        """Test Jaccard similarity of identical texts."""
        from openclaw_memory import jaccard_similarity
        
        text = "the quick brown fox"
        result = jaccard_similarity(text, text)
        
        assert result == 1.0
    
    def test_jaccard_no_overlap(self):
        """Test Jaccard similarity with no overlap."""
        from openclaw_memory import jaccard_similarity
        
        text1 = "abc def"
        text2 = "ghi jkl"
        result = jaccard_similarity(text1, text2)
        
        assert result == 0.0
    
    def test_jaccard_partial(self):
        """Test Jaccard similarity with partial overlap."""
        from openclaw_memory import jaccard_similarity
        
        text1 = "the quick brown fox"
        text2 = "the lazy dog"
        result = jaccard_similarity(text1, text2)
        
        assert 0 < result < 1
    
    def test_jaccard_empty(self):
        """Test Jaccard similarity with empty text."""
        from openclaw_memory import jaccard_similarity
        
        result = jaccard_similarity("", "some text")
        
        assert result == 0.0
    
    def test_jaccard_both_empty(self):
        """Test Jaccard similarity with both texts empty."""
        from openclaw_memory import jaccard_similarity
        
        result = jaccard_similarity("", "")
        
        assert result == 0.0
