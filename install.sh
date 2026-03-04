#!/bin/bash
# AMEM One-Command Installer
# Usage: curl -fsSL ... | bash

set -e

echo "🧠 AMEM - Agent Memory System"
echo "=============================="
echo ""

# Detect workspace
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
INSTALL_DIR="$WORKSPACE/memory_system"

echo "📁 Installing to: $INSTALL_DIR"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$WORKSPACE/memory"

# Download AMEM files
echo "📥 Downloading AMEM..."
REPO="https://raw.githubusercontent.com/ruca-radio/amem/main"

files=(
    "native/openclaw_memory.py"
    "native/embeddings.py"
    "native/auto_extract.py"
    "native/graph_memory.py"
    "native/memory_tool.py"
    "native/amem_web.py"
    "memory"
)

for file in "${files[@]}"; do
    name=$(basename "$file")
    if [ "$name" = "memory" ]; then
        curl -fsSL "$REPO/$file" -o "$WORKSPACE/amem" 2>/dev/null || true
    else
        curl -fsSL "$REPO/$file" -o "$INSTALL_DIR/$name" 2>/dev/null || true
    fi
done

# Create __init__.py
cat > "$INSTALL_DIR/__init__.py" << 'EOF'
"""AMEM - Agent Memory System"""
from .openclaw_memory import MemoryTools, OpenClawMemoryStore
__version__ = "1.0.0"
__all__ = ["MemoryTools", "OpenClawMemoryStore"]
EOF

# Make CLI executable
[ -f "$WORKSPACE/amem" ] && chmod +x "$WORKSPACE/amem"

# Create symlink for easy access
ln -sf "$WORKSPACE/amem" "$WORKSPACE/memory" 2>/dev/null || true

# Test
echo ""
echo "🧪 Testing installation..."
if python3 -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
from openclaw_memory import MemoryTools
m = MemoryTools('test')
m.remember('AMEM installed successfully', permanent=True)
print('✓ AMEM is working!')
" 2>/dev/null; then
    echo ""
    echo "✅ AMEM installed successfully!"
    echo ""
    echo "Quick start:"
    echo "  cd $WORKSPACE"
    echo "  ./amem remember 'Your memory' --permanent"
    echo "  ./amem recall 'search query'"
    echo "  ./amem web --port 8080"
    echo ""
    echo "Or use Python:"
    echo "  from memory_system import MemoryTools"
    echo "  memory = MemoryTools('default')"
else
    echo ""
    echo "⚠️  Installation may have issues. Check errors above."
    exit 1
fi