#!/bin/bash
# Install OpenClaw Memory Plugin

set -e

PLUGIN_DIR="${HOME}/.openclaw/plugins/openclaw-memory"
REPO_URL="https://github.com/ruca-radio/amem"

echo "Installing OpenClaw Memory Plugin..."
echo "===================================="

# Create plugin directory
mkdir -p "$PLUGIN_DIR"

# Download plugin files
echo "Downloading plugin files..."
curl -fsSL "${REPO_URL}/raw/main/openclaw-memory-plugin/plugin.json" -o "${PLUGIN_DIR}/plugin.json"
curl -fsSL "${REPO_URL}/raw/main/openclaw-memory-plugin/index.js" -o "${PLUGIN_DIR}/index.js"
curl -fsSL "${REPO_URL}/raw/main/openclaw-memory-plugin/bridge.py" -o "${PLUGIN_DIR}/bridge.py"

echo "Plugin installed to: $PLUGIN_DIR"
echo ""
echo "Add to ~/.openclaw/openclaw.json:"
echo '{'
echo '  "plugins": {'
echo '    "openclaw-memory": {'
echo '      "enabled": true,'
echo '      "agentId": "default",'
echo '      "embeddingProvider": "auto",'
echo '      "autoExtract": true,'
echo '      "graphMemory": true'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "Restart OpenClaw to activate the plugin."