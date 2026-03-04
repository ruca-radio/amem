# AMEM Development & Release Workflow

This document describes how to evolve and improve AMEM (Agent Memory System), with changes automatically available to all users.

## Quick Reference

```bash
# 1. Make changes locally
# 2. Test
python3 test_memory.py
python3 test_integration.py

# 3. Update version
echo "$(git rev-parse --short HEAD)" > .memory_version

# 4. Commit & push
git add -A
git commit -m "Description of changes"
git push origin main

# 5. Users get updates automatically via:
#    ./memory update
```

## What is AMEM?

AMEM (Agent Memory System) is a self-hosted memory layer for AI agents that provides:

- **Semantic memory** - Vector-based search across facts, preferences, and episodes
- **Graph memory** - Entity-relationship graph for complex queries
- **Auto-extraction** - Automatically extract information from conversations
- **Multi-provider embeddings** - HuggingFace, Ollama, OpenAI, or hash fallback
- **Codebase indexing** - Index and search code repositories
- **Web UI** - Browse and manage memories

## Development Workflow

### 1. Local Development

```bash
# Clone repo
git clone https://github.com/ruca-radio/amem.git
cd amem

# Make changes to files
# - native/*.py - Core AMEM functionality
# - memory - CLI tool
# - update.py - Self-update system
# - install.py - Installation script
# - openclaw-memory-plugin/ - OpenClaw integration

# Test changes
python3 test_memory.py
python3 test_integration.py
./memory remember "Test" --permanent
./memory recall "test"
```

### 2. Version Management

```bash
# Update version file with commit SHA
echo "$(git rev-parse --short HEAD)" > .memory_version

# Or use a semantic version
echo "1.2.0" > .memory_version
```

### 3. Testing Before Release

```bash
# Run full test suite
python3 test_memory.py

# Test installation
rm -rf /tmp/test_install
./install-lightweight.sh
# Or: python3 install.py --workspace /tmp/test_install --agent-id test

# Test update mechanism
python3 update.py --check
```

### 4. Publishing Changes

```bash
# Stage all changes
git add -A

# Commit with descriptive message
git commit -m "AMEM v1.x: Feature description

- Detail 1
- Detail 2
- Detail 3"

# Push to GitHub
git push origin main
```

## User Update Flow

Once changes are pushed, users can update:

```bash
# Check for updates
./memory update --check

# Install updates (with backup)
./memory update

# Force update even if no change detected
./memory update --force
```

## Architecture Overview

```
AMEM/
├── native/                     # Core Python implementation
│   ├── openclaw_memory.py     # Main memory system
│   ├── embeddings.py          # Multi-provider embeddings
│   ├── auto_extract.py        # Auto-extraction
│   ├── graph_memory.py        # Graph layer
│   ├── codebase_index.py      # Code indexing
│   └── web_ui.py              # Web interface
├── openclaw-memory-plugin/    # OpenClaw integration
│   ├── index.ts               # TypeScript plugin
│   ├── bridge.py              # Python bridge
│   └── package.json           # Plugin manifest
├── memory                      # CLI tool
├── install.py                  # Full installer
├── install-lightweight.sh      # Lightweight installer
├── update.py                   # Self-update
└── test_*.py                   # Test suites
```

## What Gets Updated

The update system syncs these files from GitHub:

```
native/openclaw_memory.py   - Core AMEM
native/embeddings.py        - Embedding providers
native/auto_extract.py      - Auto-extraction
native/graph_memory.py      - Graph layer
native/codebase_index.py    - Code indexing
native/web_ui.py            - Web UI
native/encryption.py        - Encryption support
memory                      - CLI tool
compress.py                 - Compression
install.py                  - Installer
test_*.py                   - Tests
README.md                   - Documentation
DEVELOPMENT.md              - This file
```

## Preserved During Update

User data is NEVER overwritten:

```
~/.openclaw/workspace/
├── MEMORY.md              ← Preserved
├── memory/                ← Preserved
│   └── YYYY-MM-DD.md
├── memory_graph/          ← Preserved
│   └── entities.json
│   └── relations.json
└── memory_system/         ← Updated
    ├── .memory_version    ← Updated
    └── *.py               ← Updated
```

## Rollback on Failure

If update fails tests, automatic rollback:

```
1. Backup created: memory_system_backup_20240304_143022/
2. Files updated
3. Tests run
4. If tests fail → Restore backup
5. User notified
```

## Release Checklist

Before pushing major changes:

- [ ] Tests pass (`python3 test_memory.py`, `python3 test_integration.py`)
- [ ] CLI works (`./memory list`)
- [ ] Web UI starts (`./memory web --port 8080`)
- [ ] Update check works (`./memory update --check`)
- [ ] Version file updated
- [ ] README updated if needed
- [ ] Commit message is descriptive

## Hotfix Workflow

For urgent fixes:

```bash
# Make fix
git add -A
git commit -m "AMEM HOTFIX: Fix critical bug X"
git push origin main

# Users get it immediately on next update check
```

## Version Numbering

Two approaches:

### 1. Git SHA (default)
```bash
echo "$(git rev-parse --short HEAD)" > .memory_version
# Result: 52af207
```

### 2. Semantic Versioning
```bash
echo "1.2.3" > .memory_version
```

Users see:
```
Local version:  52af207
Remote version: 461b52b
Update available!
```

## Automated Updates

Users can set up automatic daily checks:

```bash
# Add to crontab
crontab -e

# Add line:
0 9 * * * cd ~/.openclaw/workspace && ./memory update --check >> ~/.openclaw/update.log 2>&1
```

## Breaking Changes

If making breaking changes:

1. Update major version
2. Add migration script
3. Document in README
4. Notify users in commit message

```bash
echo "2.0.0" > .memory_version
git add -A
git commit -m "AMEM BREAKING: New API v2

Migration: Run ./memory migrate
Docs: See README.md#migration"
```

## Naming Conventions

- **AMEM** - Agent Memory System (the project)
- **memory_system/** - Installation directory
- **memory** - CLI tool
- **native/** - Core Python implementation
- **openclaw-memory-plugin/** - OpenClaw integration

## Support

- Issues: https://github.com/ruca-radio/amem/issues
- Discussions: GitHub Discussions
- Documentation: This repo + OpenClaw docs for integration