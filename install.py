#!/usr/bin/env python3
"""
OpenClaw Memory System - Self-Provisioning Installer
Installs and configures the memory system for any OpenClaw agent.

Usage:
    python install.py [--agent-id <id>] [--workspace <path>]

This script:
1. Detects OpenClaw environment
2. Installs memory system to workspace
3. Configures auto-loading for the agent
4. Sets up cron for maintenance
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Installation paths
INSTALL_DIR = Path(__file__).parent.resolve()
DEFAULT_WORKSPACE = Path.home() / ".openclaw" / "workspace"


def detect_openclaw():
    """Detect if running in OpenClaw environment"""
    return {
        "has_openclaw": shutil.which("openclaw") is not None,
        "workspace": os.getenv("OPENCLAW_WORKSPACE", str(DEFAULT_WORKSPACE)),
        "agent_id": os.getenv("OPENCLAW_AGENT_ID", "default"),
        "session_key": os.getenv("OPENCLAW_SESSION_KEY"),
    }


def install_memory_system(workspace: Path, agent_id: str, embedding_provider: Optional[str] = None):
    """Install memory system to OpenClaw workspace"""
    print(f"Installing OpenClaw Memory System to {workspace}")
    print(f"Agent ID: {agent_id}")
    if embedding_provider:
        print(f"Embedding provider: {embedding_provider}")
    
    # Create directories
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy core files
    native_src = INSTALL_DIR / "native"
    native_dst = workspace / "memory_system"
    
    if native_dst.exists():
        print(f"  Updating existing installation at {native_dst}")
        shutil.rmtree(native_dst)
    
    shutil.copytree(native_src, native_dst)
    print(f"  Copied memory system to {native_dst}")
    
    # Create agent config
    config = {
        "agent_id": agent_id,
        "memory_dir": str(memory_dir),
        "auto_load": True,
        "embedding_provider": embedding_provider,  # ollama, huggingface, openai, or null for auto
        "maintenance": {
            "enabled": True,
            "interval_hours": 24,
            "promote_threshold": 0.7,
            "decay_half_life_days": 30
        }
    }
    
    config_path = workspace / ".memory_config.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  Created config: {config_path}")
    
    # Create MEMORY.md if it doesn't exist
    memory_md = workspace / "MEMORY.md"
    if not memory_md.exists():
        memory_md.write_text(f"# {agent_id} Memory\n\nLong-term curated memory for agent.\n")
        print(f"  Created {memory_md}")
    
    # Create __init__.py for Python import
    init_file = native_dst / "__init__.py"
    init_file.write_text('''"""OpenClaw Memory System"""
from .openclaw_memory import MemoryTools, OpenClawMemoryStore

__version__ = "1.0.0"
__all__ = ["MemoryTools", "OpenClawMemoryStore"]
''')
    
    return native_dst


def setup_autoload(workspace: Path, agent_id: str, embedding_provider: Optional[str] = None):
    """Configure agent to auto-load memory system"""
    print("\nSetting up auto-load...")
    
    # Create agent bootstrap file
    bootstrap = workspace / "memory_bootstrap.py"
    
    embed_config = f'"{embedding_provider}"' if embedding_provider else "None"
    
    bootstrap.write_text(f'''#!/usr/bin/env python3
"""
Memory System Bootstrap - Auto-loaded by OpenClaw agent
Add to your agent's startup or AGENTS.md
"""
import sys
from pathlib import Path

# Add memory system to path
sys.path.insert(0, str(Path(__file__).parent / "memory_system"))

from openclaw_memory import MemoryTools
from auto_extract import AutoMemoryExtractor
from graph_memory import MemoryGraphTools

# Global memory instance
memory = MemoryTools("{agent_id}", embedding_provider={embed_config})
auto_extract = AutoMemoryExtractor("{agent_id}")
graph_memory = MemoryGraphTools("{agent_id}")

# Convenience functions for agent use
def remember(content, memory_type="fact", importance=0.5, permanent=False, extract_entities=True):
    """Store a memory with optional entity extraction"""
    if extract_entities:
        graph_memory.remember(content, permanent=permanent)
    else:
        memory.memory_write(content, permanent=permanent)

def recall(query, k=5):
    """Retrieve memories"""
    return memory.recall(query, k=k)

def get_context(query="current task", max_tokens=1500):
    """Get memory context for prompt injection"""
    return memory.context_for_prompt(query, max_tokens)

def process_conversation(user_msg, assistant_msg):
    """Process a conversation turn and auto-extract memories"""
    return auto_extract.process_turn(user_msg, assistant_msg)

def ask(question):
    """Ask questions using graph + semantic memory"""
    return graph_memory.ask(question)

print(f"[Memory System] Loaded for agent: {agent_id}")
print(f"[Memory System] Tools: remember(), recall(), get_context(), process_conversation(), ask()")
''')
    print(f"  Created bootstrap: {bootstrap}")
    
    # Update or create AGENTS.md reference
    agents_md = workspace / "AGENTS.md"
    memory_section = f"""
## Memory System

This agent has the OpenClaw Memory System installed.

**Available Tools:**
- `memory.memory_search(query, k=5)` - Search memories
- `memory.memory_get(path)` - Read memory files
- `memory.memory_write(content, permanent=False)` - Store memories
- `memory.get_context(query)` - Get prompt context

**Memory Files:**
- `MEMORY.md` - Long-term curated facts
- `memory/YYYY-MM-DD.md` - Daily episodic logs

**Auto-loaded:** `memory_bootstrap.py`
"""
    
    if agents_md.exists():
        content = agents_md.read_text()
        if "Memory System" not in content:
            agents_md.write_text(content + "\n" + memory_section)
            print(f"  Updated {agents_md}")
    else:
        agents_md.write_text(f"# Agent: {agent_id}\n" + memory_section)
        print(f"  Created {agents_md}")


def setup_maintenance(workspace: Path):
    """Set up periodic maintenance (compaction, decay)"""
    print("\nSetting up maintenance...")
    
    maintenance_script = workspace / "memory_maintenance.py"
    maintenance_script.write_text('''#!/usr/bin/env python3
"""Memory System Maintenance - Run periodically"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "memory_system"))
from openclaw_memory import MemoryTools
import json

# Load config
config_path = Path(__file__).parent / ".memory_config.json"
if config_path.exists():
    with open(config_path) as f:
        config = json.load(f)
    agent_id = config.get("agent_id", "default")
else:
    agent_id = "default"

print(f"[Memory Maintenance] Running for {agent_id}...")

memory = MemoryTools(agent_id)

# Run maintenance
stats = memory.store.stats()
print(f"  Before: {stats}")

# Promote high-value episodic memories
promoted = memory.store.store.promote_memories()
print(f"  Promoted {promoted} memories to semantic tier")

# Apply decay to old episodic memories
decayed = memory.store.store.apply_decay()
print(f"  Applied decay to {decayed} memories")

stats = memory.store.stats()
print(f"  After: {stats}")
print("[Memory Maintenance] Complete")
''')
    maintenance_script.chmod(0o755)
    print(f"  Created maintenance script: {maintenance_script}")
    
    # Try to set up cron job
    try:
        escaped_workspace = shlex.quote(str(workspace))
        escaped_script = shlex.quote(str(maintenance_script))
        cron_entry = (
            f"0 2 * * * cd {escaped_workspace} && python3 {escaped_script} >> "
            f"{escaped_workspace}/memory_maintenance.log 2>&1"
        )
        
        # Check if already installed
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "memory_maintenance" not in result.stdout:
            new_crontab = result.stdout + cron_entry + "\n"
            subprocess.run(["crontab", "-"], input=new_crontab, text=True)
            print("  Added cron job for daily maintenance at 2 AM")
        else:
            print("  Cron job already exists")
    except Exception as e:
        print(f"  Note: Could not set up cron job: {e}")
        print(f"  To enable maintenance, add this to your crontab:")
        print(f"    {cron_entry}")


def verify_installation(workspace: Path, agent_id: str, embedding_provider: Optional[str] = None):
    """Verify the installation works"""
    print("\nVerifying installation...")
    
    sys.path.insert(0, str(workspace / "memory_system"))
    try:
        from openclaw_memory import MemoryTools
        
        memory = MemoryTools(agent_id)
        
        # Show embedding info
        if hasattr(memory.store, 'embedder'):
            info = memory.store.embedder._embedder.get_info() if memory.store.embedder._embedder else {"active": "hash-fallback"}
            print(f"  Embedding provider: {info.get('active', 'unknown')}")
        
        # Test write
        test_id = memory.remember("Installation test", "fact", 0.5, permanent=True)
        print(f"  ✓ Write test passed")
        
        # Test read
        results = memory.recall("installation")
        if results:
            print(f"  ✓ Read test passed: {len(results)} results")
        
        # Test context
        context = memory.context_for_prompt("test")
        print(f"  ✓ Context generation passed")
        
        print("\n✓ Installation verified successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Install OpenClaw Memory System"
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Agent ID (default: from env or 'default')"
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="OpenClaw workspace path"
    )
    parser.add_argument(
        "--embedding",
        choices=["ollama", "huggingface", "openai", "auto"],
        default="auto",
        help="Embedding provider (default: auto-detect)"
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip verification step"
    )
    
    args = parser.parse_args()
    
    # Detect environment
    env = detect_openclaw()
    print("OpenClaw Memory System Installer")
    print("=" * 50)
    print(f"OpenClaw detected: {env['has_openclaw']}")
    
    # Determine settings
    workspace = Path(args.workspace or env['workspace'])
    agent_id = args.agent_id or env['agent_id']
    embedding_provider = None if args.embedding == "auto" else args.embedding
    
    print(f"Workspace: {workspace}")
    print(f"Agent ID: {agent_id}")
    print(f"Embedding: {args.embedding} (HuggingFace preferred)")
    print("=" * 50)
    
    # Run installation
    try:
        install_memory_system(workspace, agent_id, embedding_provider)
        setup_autoload(workspace, agent_id, embedding_provider)
        setup_maintenance(workspace)
        
        if not args.skip_verify:
            success = verify_installation(workspace, agent_id, embedding_provider)
            if not success:
                sys.exit(1)
        
        print("\n" + "=" * 50)
        print("Installation complete!")
        print(f"Memory system installed at: {workspace}/memory_system")
        print(f"Configuration: {workspace}/.memory_config.json")
        print("\nTo use in your agent:")
        print(f"  from memory_system import MemoryTools")
        print(f"  memory = MemoryTools('{agent_id}')")
        print("\nNew Features:")
        print("  • Auto-extraction: process_conversation(user_msg, assistant_msg)")
        print("  • Graph memory: ask('What technologies does user know?')")
        print("  • Web UI: python3 memory_system/web_ui.py --port 8080")
        print("\nEmbedding providers (HuggingFace preferred):")
        print("  1. HuggingFace: pip install transformers torch")
        print("     (Best quality/speed, runs locally)")
        print("  2. Ollama:      ollama run nomic-embed-text")
        print("     (Alternative local option)")
        print("  3. OpenAI:      OPENAI_API_KEY=sk-...")
        print("     (Cloud fallback)")
        print("  4. Hash:        (No setup, lower quality)")
        print("     (Zero-dependency fallback)")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Installation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
