#!/bin/bash
# Lightweight AMEM Install - CPU-only, no CUDA

set -e

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
INSTALL_DIR="$WORKSPACE/memory_system"

echo "AMEM Lightweight Installer (CPU-only)"
echo "===================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $PYTHON_VERSION"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$WORKSPACE/memory"

# Download files
echo ""
echo "Downloading AMEM..."
REPO="https://raw.githubusercontent.com/ruca-radio/amem/main"

curl -fsSL "$REPO/native/openclaw_memory.py" -o "$INSTALL_DIR/openclaw_memory.py"
curl -fsSL "$REPO/native/embeddings.py" -o "$INSTALL_DIR/embeddings.py"
curl -fsSL "$REPO/native/auto_extract.py" -o "$INSTALL_DIR/auto_extract.py"
curl -fsSL "$REPO/native/graph_memory.py" -o "$INSTALL_DIR/graph_memory.py"
curl -fsSL "$REPO/native/memory_tool.py" -o "$INSTALL_DIR/memory_tool.py"
curl -fsSL "$REPO/memory" -o "$WORKSPACE/memory"

echo "Files downloaded"

# Create __init__.py
cat > "$INSTALL_DIR/__init__.py" << 'EOF'
"""OpenClaw Memory System"""
from .openclaw_memory import MemoryTools, OpenClawMemoryStore
__version__ = "1.0.0"
__all__ = ["MemoryTools", "OpenClawMemoryStore"]
EOF

# Make CLI executable
chmod +x "$WORKSPACE/memory"

# Test import
echo ""
echo "Testing installation..."
python3 -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
from openclaw_memory import MemoryTools
m = MemoryTools('test')
m.remember('Installation test', permanent=True)
print('✓ Installation successful')
"

echo ""
echo "===================================="
echo "AMEM installed to: $INSTALL_DIR"
echo ""
echo "Usage:"
echo "  cd $WORKSPACE"
echo "  ./memory remember 'Your memory' --permanent"
echo "  ./memory recall 'search query'"
echo ""
echo "Optional: Install transformers for better embeddings"
echo "  pip3 install --user transformers torch --no-deps"
echo "===================================="