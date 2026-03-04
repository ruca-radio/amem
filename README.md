# AMEM - Agent Memory System

A production-grade, multi-tier memory architecture for AI agents. Efficient, persistent, and designed for multi-model/multi-provider environments.

## Quick Start

```bash
# One-line install (lightweight, no venv bloat)
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash

# Verify installation
python3 ~/.openclaw/workspace/memory-system/test_integration.py

# Start using
./memory remember "User prefers Python" --permanent
./memory recall "programming preferences"
```

## What is AMEM?

AMEM (Agent Memory System) is a **self-hosted memory layer** for AI agents that:

- **Stores facts, preferences, and context** across conversations
- **Retrieves relevant memories** via semantic + keyword search
- **Builds knowledge graphs** of entities and relationships
- **Auto-extracts information** from conversations
- **Works with any AI platform** (OpenClaw, Claude Code, OpenCode, etc.)

## For AI Agents: How to Use AMEM

### Installation (Do This First)

As an AI agent, you can install AMEM for your user:

```bash
# Check if AMEM is installed
if [ ! -d "$HOME/.openclaw/workspace/memory_system" ]; then
    echo "AMEM not found. Installing..."
    curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash
fi
```

### Basic Operations

#### 1. Store a Memory

```bash
./memory remember "CONTENT" [--permanent] [--type TYPE]

# Examples:
./memory remember "User prefers Python for automation" --permanent --type preference
./memory remember "Fixed Docker networking today" --type episode
./memory remember "User runs Proxmox at home" --permanent --type fact
```

**When to use:**
- User states a preference ("I like...", "I prefer...")
- User mentions a fact about themselves ("I work at...", "I use...")
- User makes a decision ("Let's use X instead of Y")
- User demonstrates a skill ("I know how to...")

#### 2. Search Memories

```bash
./memory recall "QUERY" [--limit N]

# Examples:
./memory recall "programming preferences"
./memory recall "tech stack" --limit 10
./memory recall "user infrastructure"
```

**When to use:**
- Before answering a question about user preferences
- When context from previous conversations would help
- To avoid asking repetitive questions

#### 3. Get Context for Prompts

```python
# In Python
from memory_system import MemoryTools
memory = MemoryTools("default")
context = memory.context_for_prompt("how should I respond to this request")
# Returns formatted context to inject into prompts
```

**When to use:**
- Inject relevant context into system prompts
- Personalize responses based on user history

#### 4. Query Graph Memory

```bash
./memory ask "What technologies does user know?"
./memory graph-query "Python"
```

**When to use:**
- Complex queries about relationships ("What projects use X?")
- Discovering connections between entities

### Auto-Extraction (Recommended)

Enable auto-extraction to automatically capture memories from conversations:

```python
from memory_system import MemoryTools, AutoMemoryExtractor

memory = MemoryTools("default")
extractor = AutoMemoryExtractor("default")

# After each conversation turn
facts = extractor.process_turn(user_message, assistant_response)
# Automatically extracts and stores relevant facts
```

### Update AMEM

Keep AMEM up to date:

```bash
# Check for updates
./memory update --check

# Install updates
./memory update

# Or force update
./memory update --force
```

## Architecture

```
┌─────────────────────────────────────────┐
│           Agent (Any Platform)           │
│    memory.remember() / memory.recall()  │
├─────────────────────────────────────────┤
│         AMEM Memory Tools               │
│  - Semantic search (vector + BM25)      │
│  - Graph memory (entities/relations)    │
│  - Auto-extraction                      │
├─────────────────────────────────────────┤
│  MEMORY.md  │  memory/YYYY-MM-DD.md     │
│  (long-term) │  (daily episodic)        │
└─────────────────────────────────────────┘
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Provider Embeddings** | HuggingFace → Ollama → OpenAI → Hash fallback |
| **Hybrid Search** | Vector similarity + BM25 keyword matching |
| **Graph Memory** | Entity-relationship graph for complex queries |
| **Auto-Extraction** | Automatically extract facts from conversations |
| **Codebase Indexing** | Index and search your code repositories |
| **Web UI** | Browse and search memories via web interface |
| **CLI Tools** | Command-line interface for all operations |
| **OpenClaw Plugin** | Native integration with OpenClaw agents |
| **Self-Updating** | Auto-update from GitHub with backup/rollback |

## Installation Options

### Option 1: Lightweight Install (Recommended)

No virtual environment, no CUDA dependencies:

```bash
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash
```

### Option 2: Full Install

With all features including optional ML dependencies:

```bash
git clone https://github.com/ruca-radio/amem.git
cd amem
python3 install.py --agent-id my-agent --embedding huggingface
```

### Option 3: Docker

For multi-agent deployments:

```bash
export OLLAMA_HOST=http://10.27.27.10:11434  # Your Ollama instance
docker-compose up -d
```

## Usage Guide for Agents

### CLI Reference

```bash
# Store memories
./memory remember "User prefers Python for automation" --permanent --type preference

# Search memories
./memory recall "programming preferences"
./memory recall "tech stack" --limit 10

# Graph queries
./memory ask "What technologies does user know?"
./memory graph-query "Python"

# Web UI
./memory web --port 8080

# Export/Import
./memory export --output backup.json
./memory import backup.json

# Self-update
./memory update --check
./memory update
```

### Python API for Agents

```python
from memory_system import MemoryTools, AutoMemoryExtractor, MemoryGraphTools

# Initialize
memory = MemoryTools("my-agent")
auto_extract = AutoMemoryExtractor("my-agent")
graph = MemoryGraphTools("my-agent")

# Store with metadata
memory.remember(
    content="User prefers Python for automation",
    memory_type="preference",  # fact, preference, episode, skill
    importance=0.9,
    permanent=True  # True = MEMORY.md, False = daily log
)

# Search
results = memory.recall("programming preferences", k=5)
for result in results:
    print(result)

# Get context for prompt injection
context = memory.context_for_prompt("how should I respond")
print(context)  # Formatted context string

# Auto-extract from conversation
facts = auto_extract.process_turn(
    user_message="I prefer Python over JavaScript",
    assistant_response="I'll note that preference"
)
print(f"Extracted {len(facts)} facts")

# Graph queries
answer = graph.ask("What technologies does user know?")
print(answer)

# Entity relationships
relations = graph.graph.query("Python")
for r in relations:
    print(f"{r['entity']['name']} --{r['relation']}--> ...")
```

### OpenClaw Integration

Install the plugin:

```bash
openclaw plugins install ./openclaw-memory-plugin
```

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "amem-bridge": {
        "enabled": true,
        "config": {
          "agentId": "default",
          "embeddingProvider": "auto"
        }
      }
    }
  },
  "agents": {
    "list": [{
      "id": "main",
      "tools": {
        "allow": ["amem_search", "amem_store", "amem_graph_query", "amem_ask"]
      }
    }]
  }
}
```

Then use tools directly:
- `amem_search(query="user preferences")`
- `amem_store(content="User likes Python", permanent=true)`
- `amem_graph_query(entity="Docker")`
- `amem_ask(question="What tech does user know?")`

## Memory Tiers

| Tier | Purpose | Storage | Lifetime |
|------|---------|---------|----------|
| **Working** | Current session context | In-memory | Minutes-hours |
| **Episodic** | Daily logs, events | `memory/YYYY-MM-DD.md` | Days-weeks |
| **Semantic** | Core facts, preferences | `MEMORY.md` | Permanent |

## Embedding Providers

| Provider | Priority | Quality | Setup |
|----------|----------|---------|-------|
| **HuggingFace** | 1st | ⭐⭐⭐ Excellent | `pip install transformers torch` |
| **Ollama** | 2nd | ⭐⭐⭐ Excellent | `ollama run nomic-embed-text` |
| **OpenAI** | 3rd | ⭐⭐⭐ Excellent | `OPENAI_API_KEY=sk-...` |
| **Hash** | Fallback | ⭐☆☆ Basic | No setup required |

## Configuration

Environment variables:

```bash
# Workspace location
export OPENCLAW_WORKSPACE=~/.openclaw/workspace

# Embedding provider
export OLLAMA_HOST=http://localhost:11434
export HF_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
export OPENAI_API_KEY=sk-...

# AMEM agent ID
export AMEM_AGENT_ID=default
```

## File Structure

```
~/.openclaw/workspace/
├── MEMORY.md                    # Long-term curated memory
├── memory/                      # Daily episodic logs
│   └── 2026-03-04.md
├── memory_system/               # AMEM installation
│   ├── __init__.py
│   ├── openclaw_memory.py      # Core memory system
│   ├── embeddings.py           # Multi-provider embeddings
│   ├── auto_extract.py         # Auto-extraction
│   ├── graph_memory.py         # Graph layer
│   ├── codebase_index.py       # Code indexing
│   └── web_ui.py               # Web interface
├── memory                       # CLI tool
└── .memory_config.json         # Configuration
```

## Best Practices for Agents

### 1. Store Important Facts Immediately

When a user shares something important, store it right away:

```python
# Good: Store immediately
if "I prefer" in user_message or "I like" in user_message:
    memory.remember(user_message, memory_type="preference", permanent=True)
```

### 2. Search Before Asking

Before asking the user something, check if you already know:

```python
# Good: Check memory first
results = memory.recall("user email")
if results:
    email = extract_email(results[0])
else:
    email = ask_user("What's your email?")
```

### 3. Use Context Injection

Inject relevant memories into your context:

```python
context = memory.context_for_prompt("current task")
system_prompt = f"""
## Relevant Context
{context}

## Instructions
...
"""
```

### 4. Update Regularly

Keep AMEM updated:

```bash
./memory update --check  # Check weekly
```

## Development

```bash
# Clone repo
git clone https://github.com/ruca-radio/amem.git
cd amem

# Run tests
python3 test_memory.py
python3 test_integration.py

# Update version
echo "$(git rev-parse --short HEAD)" > .memory_version

# Commit and push
git add -A
git commit -m "Description"
git push origin main
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed workflow.

## Troubleshooting

### "memory_system not found"

Run the lightweight installer:
```bash
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash
```

### "No ML provider available"

Install transformers for better embeddings:
```bash
pip3 install --user transformers torch --no-deps
```

Or use Ollama:
```bash
ollama run nomic-embed-text
```

### Venv bloat (7GB+ with CUDA)

Use the lightweight install which doesn't use a virtual environment:
```bash
./install-lightweight.sh
```

## License

MIT

## Links

- Repository: https://github.com/ruca-radio/amem
- Issues: https://github.com/ruca-radio/amem/issues
- Documentation: https://docs.openclaw.ai (for OpenClaw integration)