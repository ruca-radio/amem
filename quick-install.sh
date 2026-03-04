#!/bin/bash
# One-line installer for OpenClaw Memory System
# Usage: curl -fsSL https://raw.githubusercontent.com/ruca-radio/amem/main/quick-install.sh | bash

set -e

REPO_URL="https://github.com/ruca-radio/amem.git"
INSTALL_DIR="${HOME}/.openclaw/amem-install"
WORKSPACE="${OPENCLAW_WORKSPACE:-${HOME}/.openclaw/workspace}"
AGENT_ID="${OPENCLAW_AGENT_ID:-default}"

echo "OpenClaw Memory System - Quick Installer"
echo "========================================"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --agent-id)
            AGENT_ID="$2"
            shift 2
            ;;
        --workspace)
            WORKSPACE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check dependencies
if ! command -v git &> /dev/null; then
    echo "Error: git is required"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required"
    exit 1
fi

# Clone repository
echo ""
echo "Cloning repository..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi
git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"

# Run installer
echo ""
echo "Running installer..."
cd "$INSTALL_DIR"
python3 install.py --agent-id "$AGENT_ID" --workspace "$WORKSPACE"

# Cleanup
echo ""
echo "Cleaning up..."
rm -rf "$INSTALL_DIR"

echo ""
echo "========================================"
echo "Installation complete!"
echo ""
echo "Memory system is ready to use."
echo "Add to your agent's AGENTS.md:"
echo "  from memory_system import MemoryTools"
echo "  memory = MemoryTools('$AGENT_ID')"
echo "========================================"