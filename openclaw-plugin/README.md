# AMEM OpenClaw Plugin

Official OpenClaw plugin for AMEM (Agent Memory System).

## Installation

### Prerequisites

First, install AMEM Python backend:

```bash
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash
```

### Install Plugin

```bash
# From npm (when published)
openclaw plugins install @ruca/amem

# From local path
cd openclaw-plugin
npm install
npm run build
openclaw plugins install .

# Or link for development
openclaw plugins install -l .
```

## Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "@ruca/amem": {
        "enabled": true,
        "config": {
          "agentId": "default",
          "embeddingProvider": "auto",
          "autoExtract": true,
          "graphMemory": true
        }
      }
    }
  }
}
```

## Tools Provided

- `amem_search(query, k=5)` - Search AMEM memory
- `amem_store(content, permanent=false)` - Store memory
- `amem_graph_query(entity)` - Query graph relationships
- `amem_ask(question)` - Ask questions using memory

## Development

```bash
npm install
npm run build
# or: npm run dev (watch mode)
```

## Architecture

```
OpenClaw (TypeScript)
    ↓
openclaw-plugin (TypeScript)
    ↓ (spawn Python process)
bridge.py (Python)
    ↓
AMEM native/*.py
```

## Links

- AMEM: https://github.com/ruca-radio/amem
- OpenClaw: https://openclaw.ai