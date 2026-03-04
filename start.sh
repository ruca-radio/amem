#!/bin/bash
# AMEM - Start the complete memory system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧠 AMEM - Agent Memory System"
echo "=============================="

# Check if already running
if pgrep -f "amem_server.py" > /dev/null; then
    echo "✓ AMEM server already running"
    echo ""
    echo "Access:"
    echo "  Web UI:   http://localhost:8080"
    echo "  HTTP API: http://localhost:8080/api/"
    echo "  WebSocket: ws://localhost:8081"
    exit 0
fi

# Install dependencies if needed
if ! python3 -c "import websockets" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install --user websockets requests 2>/dev/null || pip3 install websockets requests
fi

# Start server
echo "🚀 Starting AMEM server..."
python3 amem_server.py --http-port 8080 --ws-port 8081 &
echo $! > .amem.pid

sleep 2

echo ""
echo "✅ AMEM is running!"
echo ""
echo "Access Points:"
echo "  🌐 Web UI:    http://localhost:8080"
echo "  🔌 HTTP API:  http://localhost:8080/api/"
echo "  📡 WebSocket: ws://localhost:8081"
echo ""
echo "Quick Test:"
echo "  curl -X POST http://localhost:8080/api/stats -d '{\"agent_id\":\"default\"}'"
echo ""
echo "Stop: kill $(cat .amem.pid)"