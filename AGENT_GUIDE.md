# AMEM Agent Guide

Complete guide for AI agents using AMEM (Agent Memory System).

## Quick Reference for Agents

```bash
# Install AMEM (run once)
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash

# Store memory
./memory remember "CONTENT" --permanent [--type TYPE]

# Search memory  
./memory recall "QUERY"

# Update AMEM
./memory update
```

## When to Use AMEM

### Store Memories When:
- User states a preference ("I prefer...", "I like...", "I want...")
- User mentions personal facts ("I work at...", "I live in...", "I use...")
- User makes decisions ("Let's go with X", "I chose Y")
- User demonstrates knowledge ("I know how to...", "I'm skilled at...")
- User shares constraints ("I can't...", "I never...", "I always...")

### Search Memories When:
- Before asking the user something you might already know
- When personalizing a response
- When context from previous conversations would help
- When avoiding repetitive questions

## Installation Commands

### Check if AMEM is Installed

```bash
if [ -d "$HOME/.openclaw/workspace/memory_system" ]; then
    echo "AMEM is installed"
else
    echo "AMEM not found"
fi
```

### Install AMEM

```bash
# Method 1: One-line install (recommended)
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash

# Method 2: Manual install
git clone https://github.com/ruca-radio/amem.git /tmp/amem
mkdir -p ~/.openclaw/workspace/memory_system
cp /tmp/amem/native/*.py ~/.openclaw/workspace/memory_system/
echo "__all__ = ['MemoryTools', 'OpenClawMemoryStore']" > ~/.openclaw/workspace/memory_system/__init__.py
cp /tmp/amem/memory ~/.openclaw/workspace/
chmod +x ~/.openclaw/workspace/memory
```

### Verify Installation

```bash
python3 ~/.openclaw/workspace/memory-system/test_integration.py
```

## Update Commands

### Check for Updates

```bash
cd ~/.openclaw/workspace
./memory update --check
```

### Install Updates

```bash
cd ~/.openclaw/workspace
./memory update
```

### Force Update (if needed)

```bash
cd ~/.openclaw/workspace
./memory update --force
```

## Storage Commands

### Store a Fact

```bash
./memory remember "User works at Company X as a senior engineer" --permanent --type fact
```

### Store a Preference

```bash
./memory remember "User prefers dark mode for all applications" --permanent --type preference
```

### Store an Episode (Daily Log)

```bash
./memory remember "Debugged Docker networking issue today" --type episode
```

### Store a Skill

```bash
./memory remember "User is skilled with Kubernetes and Docker" --permanent --type skill
```

## Retrieval Commands

### Basic Search

```bash
./memory recall "programming preferences"
```

### Search with Limit

```bash
./memory recall "tech stack" --limit 10
```

### Get Context for Prompts (Python)

```python
from memory_system import MemoryTools
memory = MemoryTools("default")
context = memory.context_for_prompt("how should I respond")
print(context)
```

## Graph Memory Commands

### Ask a Question

```bash
./memory ask "What technologies does user know?"
./memory ask "What projects is user working on?"
```

### Query Entity Relationships

```bash
./memory graph-query "Python"
./memory graph-query "Docker"
```

## Python API for Agents

### Initialize

```python
from memory_system import MemoryTools, AutoMemoryExtractor, MemoryGraphTools

memory = MemoryTools("default")
auto_extract = AutoMemoryExtractor("default")
graph = MemoryGraphTools("default")
```

### Store with Full Metadata

```python
memory.remember(
    content="User prefers Python for automation scripts",
    memory_type="preference",  # fact, preference, episode, skill
    importance=0.9,            # 0.0 to 1.0
    permanent=True             # True = MEMORY.md, False = daily log
)
```

### Search and Use Results

```python
results = memory.recall("programming preferences", k=5)

if results:
    print("Found memories:")
    for r in results:
        print(f"  - {r}")
else:
    print("No relevant memories found")
```

### Auto-Extract from Conversations

```python
# After each conversation turn
facts = auto_extract.process_turn(
    user_message="I prefer Python over JavaScript",
    assistant_response="I'll note that you prefer Python"
)

print(f"Extracted {len(facts)} facts automatically")
```

### Get Context for System Prompts

```python
# Get relevant context for current task
context = memory.context_for_prompt(
    query="user communication preferences",
    max_tokens=1000
)

system_prompt = f"""
## Relevant Context from Memory
{context}

## Your Task
Respond to the user based on the above context.
"""
```

### Graph Queries

```python
# Ask natural language questions
answer = graph.ask("What technologies does user work with?")
print(answer)

# Query specific entities
relations = graph.graph.query("Python")
for r in relations:
    print(f"{r['entity']['name']} ({r['entity']['type']})")
```

## Integration Patterns

### Pattern 1: Store on Preference Detection

```python
def handle_user_message(message):
    # Check for preferences
    if any(phrase in message.lower() for phrase in ["i prefer", "i like", "i want"]):
        memory.remember(message, memory_type="preference", permanent=True)
    
    # Check for facts
    if any(phrase in message.lower() for phrase in ["i work at", "i use", "i have"]):
        memory.remember(message, memory_type="fact", permanent=True)
    
    # Process message...
```

### Pattern 2: Search Before Ask

```python
def get_user_info(info_type):
    # Search memory first
    results = memory.recall(info_type, k=3)
    
    if results:
        # Extract info from memory
        return extract_from_results(results)
    else:
        # Ask user
        return ask_user(f"What is your {info_type}?")
```

### Pattern 3: Context Injection

```python
def generate_response(user_message):
    # Get relevant context
    context = memory.context_for_prompt(user_message)
    
    # Build prompt with context
    prompt = f"""
## Relevant Context
{context}

## User Message
{user_message}

## Your Response
"""
    
    return call_llm(prompt)
```

## Common Workflows

### First-Time Setup

```bash
# 1. Install AMEM
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash

# 2. Verify
python3 ~/.openclaw/workspace/memory-system/test_integration.py

# 3. Store initial preferences
./memory remember "User prefers direct technical communication" --permanent --type preference
```

### Daily Usage

```bash
# Check for updates (weekly)
./memory update --check

# Store important facts as they come up
./memory remember "User decided to use Docker Compose" --permanent --type decision

# Search when needed
./memory recall "docker decisions"
```

### Backup and Restore

```bash
# Export memories
./memory export --output amem-backup-$(date +%Y%m%d).json

# Import memories
./memory import amem-backup-20240304.json
```

## Error Handling

### "memory_system not found"

```bash
# Reinstall AMEM
curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/install-lightweight.sh | bash
```

### "No ML provider available"

```bash
# Option 1: Use hash embeddings (no install needed)
# Already works, just uses lower quality embeddings

# Option 2: Install HuggingFace (better quality)
pip3 install --user transformers torch --no-deps

# Option 3: Use Ollama (local, good quality)
ollama run nomic-embed-text
```

### Import Errors

```python
# If import fails, check path
import sys
sys.path.insert(0, '/root/.openclaw/workspace/memory_system')
from openclaw_memory import MemoryTools
```

## Best Practices

1. **Store immediately** - Don't wait, store important facts right away
2. **Be specific** - "User prefers Python" is better than "User likes programming"
3. **Use permanent storage** for facts and preferences that won't change
4. **Use daily logs** for ephemeral events and episodes
5. **Search before asking** - Always check memory before asking the user
6. **Update regularly** - Keep AMEM updated with `./memory update`
7. **Use types** - Mark memories as fact, preference, episode, or skill
8. **Set importance** - High importance (0.8+) for critical facts

## Support

- Issues: https://github.com/ruca-radio/amem/issues
- Repository: https://github.com/ruca-radio/amem