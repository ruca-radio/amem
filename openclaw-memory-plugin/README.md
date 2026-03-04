# AMEM OpenClaw Plugin

TypeScript plugin that bridges OpenClaw to AMEM (Agent Memory System).

## What is AMEM?

AMEM is a self-hosted memory layer for AI agents providing:
- Semantic memory search (vector + BM25)
- Graph memory (entities and relationships)
- Auto-extraction from conversations
- Multi-provider embeddings
- Codebase indexing

## Installation

```bash
# Install from local path
openclaw plugins install ./openclaw-memory-plugin

# Or link for development
openclaw plugins install -l ./openclaw-memory-plugin
```

## Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "amem-bridge": {
        "enabled": true,
        "config": {
          "agentId": "default",
          "embeddingProvider": "auto",
          "autoExtract": true,
          "graphMemory": true
        }
      }
    }
  },
  "agents": {
    "list": [
      {
        "id": "main",
        "tools": {
          "allow": ["amem_search", "amem_store", "amem_graph_query", "amem_ask"]
        }
      }
    ]
  }
}
```

## Tools Provided

- `amem_search(query, k=5)` - Search AMEM memory
- `amem_store(content, permanent=false)` - Store memory
- `amem_graph_query(entity)` - Query graph relationships
- `amem_ask(question)` - Ask questions using memory

## Requirements

- Python 3.11+
- AMEM installed (`./install-lightweight.sh`)
- See main AMEM repo for setup: https://github.com/ruca-radio/amem

## Architecture

```
OpenClaw Agent
    ↓ (TypeScript plugin)
index.ts - Tool registration
    ↓ (spawn Python process)
bridge.py - Python bridge
    ↓ (import)
AMEM native/*.py - Core memory system
```

The plugin spawns a persistent Python process that handles all memory operations,
communicating via JSON over stdin/stdout.

## Differences from Built-in Memory

OpenClaw has built-in memory (`memory_search`, `memory_get`) that uses:
- Markdown files (`MEMORY.md`, `memory/*.md`)
- SQLite vector index
- Hybrid BM25 + embeddings

AMEM adds:
- Python-native implementation
- Graph memory layer (entities/relationships)
- Auto-extraction from conversations
- Multi-provider embeddings (HuggingFace primary)
- Codebase indexing
- CLI tools

Use whichever fits your workflow, or use both together.

## Development

```bash
cd openclaw-memory-plugin
npm install
npm run build
# Or: npm run dev (watch mode)
```

## Links

- AMEM Repository: https://github.com/ruca-radio/amem
- AMEM Issues: https://github.com/ruca-radio/amem/issues