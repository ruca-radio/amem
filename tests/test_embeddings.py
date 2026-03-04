"""
Unit tests for embedding providers.
Tests Ollama, HuggingFace, OpenAI, and hash fallback providers.
"""
import pytest
import json
import sys
import math
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

sys.path.insert(0, "/root/.openclaw/workspace/memory_system")


class TestSimpleHashEmbedding:
    """Tests for the hash-based fallback embedding."""
    
    def test_hash_embedding_initialization(self):
        """Test SimpleHashEmbedding initialization."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        assert embedder.dim == 384
        assert embedder.name == "hash-fallback"
    
    def test_hash_embedding_single_text(self):
        """Test embedding a single text."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result = embedder.embed(["test text"])
        
        assert len(result) == 1
        assert len(result[0]) == 384
        # Check normalization
        norm = math.sqrt(sum(x*x for x in result[0]))
        assert abs(norm - 1.0) < 0.01
    
    def test_hash_embedding_multiple_texts(self):
        """Test embedding multiple texts."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        texts = ["text one", "text two", "text three"]
        result = embedder.embed(texts)
        
        assert len(result) == 3
        for emb in result:
            assert len(emb) == 384
    
    def test_hash_embedding_deterministic(self):
        """Test that same text produces same embedding."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result1 = embedder.embed(["test text"])
        result2 = embedder.embed(["test text"])
        
        assert result1[0] == result2[0]
    
    def test_hash_embedding_different_texts(self):
        """Test that different texts produce different embeddings."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result1 = embedder.embed(["text one"])
        result2 = embedder.embed(["text two"])
        
        assert result1[0] != result2[0]
    
    def test_hash_embedding_empty_list(self):
        """Test embedding empty list."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result = embedder.embed([])
        
        assert result == []
    
    def test_hash_embedding_unicode(self):
        """Test embedding unicode text."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        texts = [
            "用户喜欢中文内容",
            "ユーザーは日本語が好き",
            "Пользователь любит русский",
            "🎉🚀💻"
        ]
        result = embedder.embed(texts)
        
        assert len(result) == 4
        for emb in result:
            assert len(emb) == 384
    
    def test_hash_embedding_long_text(self):
        """Test embedding very long text."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        long_text = "x" * 10000
        result = embedder.embed([long_text])
        
        assert len(result) == 1
        assert len(result[0]) == 384


class TestOllamaProvider:
    """Tests for Ollama embedding provider."""
    
    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_ollama_provider_check_available_success(self, mock_request, mock_urlopen):
        """Test Ollama availability check when server is running."""
        from embeddings import OllamaProvider
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "models": [{"name": "nomic-embed-text:latest"}]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        provider = OllamaProvider()
        assert provider.available == True
    
    @patch('urllib.request.urlopen')
    def test_ollama_provider_check_available_failure(self, mock_urlopen):
        """Test Ollama availability check when server is not running."""
        from embeddings import OllamaProvider
        import urllib.error
        
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        
        provider = OllamaProvider()
        assert provider.available == False
    
    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_ollama_embed(self, mock_request, mock_urlopen):
        """Test Ollama embedding."""
        from embeddings import OllamaProvider
        
        # Create a proper mock context manager
        class MockResponse:
            def __init__(self, data, status=200):
                self._data = data
                self.status = status
            def read(self):
                return self._data.encode() if isinstance(self._data, str) else self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        
        # Mock the tags response (availability check)
        tags_response = MockResponse(json.dumps({
            "models": [{"name": "nomic-embed-text:latest"}]
        }))
        
        # Mock the embeddings response
        embed_response = MockResponse(json.dumps({
            "embedding": [0.1] * 768
        }))
        
        mock_urlopen.side_effect = [tags_response, embed_response]
        
        provider = OllamaProvider()
        result = provider.embed(["test text"])
        
        assert len(result) == 1
        assert len(result[0]) == 768
    
    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    def test_ollama_embed_multiple(self, mock_request, mock_urlopen):
        """Test Ollama embedding multiple texts."""
        from embeddings import OllamaProvider
        
        # Create a proper mock context manager
        class MockResponse:
            def __init__(self, data, status=200):
                self._data = data
                self.status = status
            def read(self):
                return self._data.encode() if isinstance(self._data, str) else self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        
        # Mock the tags response (availability check)
        tags_response = MockResponse(json.dumps({
            "models": [{"name": "nomic-embed-text:latest"}]
        }))
        
        # Mock the embeddings responses
        embed_response = MockResponse(json.dumps({
            "embedding": [0.1] * 768
        }))
        
        mock_urlopen.side_effect = [
            tags_response,
            embed_response,
            embed_response,
            embed_response
        ]
        
        provider = OllamaProvider()
        result = provider.embed(["text one", "text two", "text three"])
        
        assert len(result) == 3


class TestOpenAIProvider:
    """Tests for OpenAI embedding provider."""
    
    def test_openai_provider_check_available_with_key(self):
        """Test OpenAI availability when API key is set."""
        from embeddings import OpenAIProvider, OPENAI_KEY
        
        # Save original key
        orig_key = OPENAI_KEY
        
        # Temporarily set the module-level key
        import embeddings
        embeddings.OPENAI_KEY = 'test-key'
        
        try:
            provider = OpenAIProvider()
            assert provider.available == True
        finally:
            # Restore original key
            embeddings.OPENAI_KEY = orig_key
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': ''})
    def test_openai_provider_check_available_without_key(self):
        """Test OpenAI availability when API key is not set."""
        from embeddings import OpenAIProvider
        
        provider = OpenAIProvider()
        assert provider.available == False
    
    @patch('urllib.request.urlopen')
    @patch('urllib.request.Request')
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_openai_embed(self, mock_request, mock_urlopen):
        """Test OpenAI embedding."""
        from embeddings import OpenAIProvider
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "data": [
                {"index": 0, "embedding": [0.1] * 1536},
                {"index": 1, "embedding": [0.2] * 1536}
            ]
        }).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        provider = OpenAIProvider()
        result = provider.embed(["text one", "text two"])
        
        assert len(result) == 2
        assert len(result[0]) == 1536
        assert len(result[1]) == 1536
    
    @patch('urllib.request.urlopen')
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}, clear=False)
    def test_openai_embed_empty(self, mock_urlopen):
        """Test OpenAI embedding with empty list."""
        from embeddings import OpenAIProvider
        
        # Create a proper mock context manager
        class MockResponse:
            def __init__(self, data, status=200):
                self._data = data
                self.status = status
            def read(self):
                return self._data.encode() if isinstance(self._data, str) else self._data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        
        mock_response = MockResponse(json.dumps({
            "data": []
        }))
        mock_urlopen.return_value = mock_response
        
        provider = OpenAIProvider()
        result = provider.embed([])
        
        # Empty list should return empty or handle gracefully
        assert isinstance(result, list)


class TestHuggingFaceProvider:
    """Tests for HuggingFace embedding provider."""
    
    @patch('importlib.util.find_spec')
    def test_huggingface_provider_check_available_with_deps(self, mock_find_spec):
        """Test HuggingFace availability when dependencies are installed."""
        from embeddings import HuggingFaceProvider
        
        mock_find_spec.side_effect = lambda name: MagicMock() if name in ['transformers', 'torch'] else None
        
        provider = HuggingFaceProvider()
        assert provider.available == True
    
    @patch('importlib.util.find_spec')
    def test_huggingface_provider_check_available_without_deps(self, mock_find_spec):
        """Test HuggingFace availability when dependencies are missing."""
        from embeddings import HuggingFaceProvider
        
        mock_find_spec.return_value = None
        
        provider = HuggingFaceProvider()
        assert provider.available == False
    
    @patch('importlib.util.find_spec')
    def test_huggingface_provider_dim(self, mock_find_spec):
        """Test HuggingFace provider dimension."""
        from embeddings import HuggingFaceProvider
        
        mock_find_spec.side_effect = lambda name: MagicMock() if name in ['transformers', 'torch'] else None
        
        provider = HuggingFaceProvider()
        assert provider.dim == 384  # MiniLM default


class TestEmbeddingProviderBase:
    """Tests for EmbeddingProvider base class."""
    
    def test_base_provider_not_implemented(self):
        """Test that base provider embed method raises NotImplementedError."""
        from embeddings import EmbeddingProvider
        
        provider = EmbeddingProvider("test")
        with pytest.raises(NotImplementedError):
            provider.embed(["test"])


class TestMultiProviderEmbedding:
    """Tests for multi-provider embedding with fallback."""
    
    def test_multi_provider_initialization(self):
        """Test MultiProviderEmbedding initialization."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        assert embedder is not None
        assert embedder.dim > 0
    
    def test_multi_provider_embed_single(self):
        """Test embedding single text."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        result = embedder.embed("test text")
        
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_multi_provider_embed_batch(self):
        """Test embedding batch of texts."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        texts = ["text one", "text two", "text three"]
        result = embedder.embed_batch(texts)
        
        assert len(result) == 3
        for emb in result:
            assert isinstance(emb, list)
            assert len(emb) > 0
    
    def test_multi_provider_embed_empty(self):
        """Test embedding empty list."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        result = embedder.embed_batch([])
        
        assert result == []
    
    def test_multi_provider_get_info(self):
        """Test getting provider info."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        info = embedder.get_info()
        
        assert "active" in info
        assert "dimension" in info
        assert "available" in info
        assert isinstance(info["available"], dict)
    
    def test_multi_provider_preferred(self):
        """Test preferred provider selection."""
        from embeddings import MultiProviderEmbedding
        
        # Should not fail even with invalid preferred
        embedder = MultiProviderEmbedding(preferred="nonexistent")
        assert embedder is not None
    
    def test_get_embedder_singleton(self):
        """Test get_embedder returns singleton."""
        from embeddings import get_embedder, MultiProviderEmbedding
        
        embedder1 = get_embedder()
        embedder2 = get_embedder()
        
        assert embedder1 is embedder2
    
    def test_multi_provider_fallback_on_error(self):
        """Test that provider falls back on error."""
        from embeddings import MultiProviderEmbedding
        
        embedder = MultiProviderEmbedding()
        
        # Force an error by temporarily breaking the active provider
        if embedder.active_provider:
            original_embed = embedder.active_provider.embed
            embedder.active_provider.embed = MagicMock(side_effect=Exception("Test error"))
            
            try:
                result = embedder.embed_batch(["test text"])
                # Should fall back to hash embedding
                assert isinstance(result, list)
                assert len(result) == 1
            finally:
                embedder.active_provider.embed = original_embed


class TestEmbeddingEdgeCases:
    """Edge case tests for embeddings."""
    
    def test_embedding_unicode_various(self):
        """Test embedding various unicode strings."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        texts = [
            "",  # Empty
            "a",  # Single char
            "   ",  # Whitespace
            "Hello, World!",
            "用户喜欢中文内容",
            "🎉🚀💻",
            "Mixed: 中文 and English 🎉",
            "Special chars: @#$%^&*()",
            "New\nLines\nAnd\tTabs",
        ]
        
        result = embedder.embed(texts)
        assert len(result) == len(texts)
        for emb in result:
            assert len(emb) == 384
            # Check normalization
            norm = math.sqrt(sum(x*x for x in emb))
            assert abs(norm - 1.0) < 0.01 or norm == 0.0
    
    def test_embedding_similarity(self):
        """Test that similar texts have similar embeddings."""
        from embeddings import SimpleHashEmbedding
        
        def cosine_sim(a, b):
            dot = sum(x*y for x, y in zip(a, b))
            na = math.sqrt(sum(x*x for x in a))
            nb = math.sqrt(sum(x*x for x in b))
            return dot / (na * nb) if na > 0 and nb > 0 else 0.0
        
        embedder = SimpleHashEmbedding(dim=384)
        
        text1 = "The cat sat on the mat"
        text2 = "The cat sat on the mat"  # Identical
        text3 = "A dog ran in the park"    # Different
        
        emb1 = embedder.embed([text1])[0]
        emb2 = embedder.embed([text2])[0]
        emb3 = embedder.embed([text3])[0]
        
        sim_identical = cosine_sim(emb1, emb2)
        sim_different = cosine_sim(emb1, emb3)
        
        assert sim_identical == pytest.approx(1.0, abs=1e-10)  # Identical texts
        assert sim_different < 1.0   # Different texts
    
    def test_embedding_dimension_consistency(self):
        """Test that all embeddings have consistent dimensions."""
        from embeddings import SimpleHashEmbedding
        
        dims = [128, 256, 384, 512, 768]
        
        for dim in dims:
            embedder = SimpleHashEmbedding(dim=dim)
            result = embedder.embed(["test"])
            assert len(result[0]) == dim
    
    def test_embedding_empty_string(self):
        """Test embedding empty string."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result = embedder.embed([""])
        
        assert len(result) == 1
        assert len(result[0]) == 384
    
    def test_embedding_single_token(self):
        """Test embedding single token."""
        from embeddings import SimpleHashEmbedding
        
        embedder = SimpleHashEmbedding(dim=384)
        result = embedder.embed(["hello"])
        
        assert len(result) == 1
        assert len(result[0]) == 384
        # Should be normalized
        norm = math.sqrt(sum(x*x for x in result[0]))
        assert abs(norm - 1.0) < 0.01
