"""
Pytest fixtures and configuration for AMEM tests.
"""
import pytest
import tempfile
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add the memory_system path for imports
sys.path.insert(0, "/root/.openclaw/workspace/memory_system")


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for isolated tests."""
    temp_dir = tempfile.mkdtemp(prefix="amem_test_")
    # Create necessary subdirectories
    memory_dir = Path(temp_dir) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_memory_dir(temp_workspace):
    """Create a mock memory directory structure."""
    memory_dir = temp_workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


@pytest.fixture
def mock_env_vars(temp_workspace):
    """Set up environment variables for testing and patch the module paths."""
    old_env = os.environ.copy()
    os.environ["OPENCLAW_WORKSPACE"] = str(temp_workspace)
    os.environ["OLLAMA_HOST"] = "http://localhost:11434"
    os.environ["OPENAI_API_KEY"] = ""
    
    # We need to patch the module-level variables after import
    # since they're set at import time
    import openclaw_memory
    import amem_web
    
    # Save original values
    orig_workspace = openclaw_memory.WORKSPACE_DIR
    orig_memory_dir = openclaw_memory.MEMORY_DIR
    orig_memory_md = openclaw_memory.MEMORY_MD
    orig_amem_workspace = amem_web.WORKSPACE_DIR
    
    # Set new values
    openclaw_memory.WORKSPACE_DIR = temp_workspace
    openclaw_memory.MEMORY_DIR = temp_workspace / "memory"
    openclaw_memory.MEMORY_MD = temp_workspace / "MEMORY.md"
    amem_web.WORKSPACE_DIR = temp_workspace
    
    yield
    
    # Restore original values
    os.environ.clear()
    os.environ.update(old_env)
    openclaw_memory.WORKSPACE_DIR = orig_workspace
    openclaw_memory.MEMORY_DIR = orig_memory_dir
    openclaw_memory.MEMORY_MD = orig_memory_md
    amem_web.WORKSPACE_DIR = orig_amem_workspace


@pytest.fixture
def mock_ollama_response():
    """Mock response for Ollama API."""
    return {
        "embedding": [0.1] * 768  # nomic-embed-text dimension
    }


@pytest.fixture
def mock_openai_response():
    """Mock response for OpenAI API."""
    return {
        "data": [
            {"index": 0, "embedding": [0.2] * 1536},
            {"index": 1, "embedding": [0.3] * 1536}
        ]
    }


@pytest.fixture
def sample_memories():
    """Sample memory contents for testing."""
    return {
        "facts": [
            "User runs Proxmox infrastructure at home lab",
            "User prefers Python for automation tasks",
            "System uses Docker for containerization"
        ],
        "preferences": [
            "User prefers direct technical communication",
            "User likes dark mode interfaces",
            "User prefers CLI over GUI"
        ],
        "episodes": [
            "Debugged Docker networking issue today",
            "Set up new VM on Proxmox yesterday",
            "Learned about vector databases"
        ],
        "unicode_content": [
            "用户喜欢中文内容",  # Chinese
            "ユーザーは日本語が好き",  # Japanese
            "Пользователь любит русский",  # Russian
            "User likes emojis 🎉🚀💻"
        ],
        "edge_cases": [
            "",  # Empty string
            "a",  # Single character
            "   ",  # Whitespace only
            "x" * 10000,  # Very long content
        ]
    }


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = MagicMock()
    provider.name = "mock"
    provider.available = True
    provider.dim = 384
    provider.embed.return_value = [[0.1] * 384]
    return provider


@pytest.fixture
def mock_http_response():
    """Helper to create mock HTTP responses."""
    def _create_response(status=200, data=None):
        response = MagicMock()
        response.status = status
        response.read.return_value = str.encode(str(data)) if data else b'{}'
        return response
    return _create_response


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for async tests."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
