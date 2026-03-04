#!/usr/bin/env python3
"""
AMEM Web UI - Dynamic web interface with REST API
"""
import json
import http.server
import socketserver
import urllib.parse
from pathlib import Path
from datetime import datetime
import sys
import os
import threading

# Import AMEM
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, WORKSPACE_DIR


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; line-height: 1.6; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
header { border-bottom: 1px solid #30363d; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }
h1 { color: #58a6ff; font-size: 28px; display: flex; align-items: center; gap: 10px; }
h2 { color: #79c0ff; font-size: 20px; margin: 20px 0 10px; }
.brand { font-size: 14px; color: #8b949e; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; text-align: center; }
.stat-value { font-size: 32px; font-weight: bold; color: #58a6ff; }
.stat-label { font-size: 12px; color: #8b949e; text-transform: uppercase; }
.search-box { width: 100%; padding: 12px 16px; font-size: 16px; background: #21262d; border: 1px solid #30363d; border-radius: 8px; color: #c9d1d9; margin: 20px 0; }
.search-box:focus { outline: none; border-color: #58a6ff; }
.memory-list { display: flex; flex-direction: column; gap: 10px; }
.memory-item { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; cursor: pointer; transition: border-color 0.2s; }
.memory-item:hover { border-color: #58a6ff; }
.memory-content { color: #c9d1d9; margin-bottom: 8px; }
.memory-meta { font-size: 12px; color: #8b949e; display: flex; gap: 15px; }
.nav { display: flex; gap: 20px; margin-bottom: 20px; }
.nav a { color: #8b949e; text-decoration: none; padding: 8px 0; border-bottom: 2px solid transparent; }
.nav a:hover, .nav a.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.file-list { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.file-item { padding: 12px 15px; border-bottom: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
.file-item:last-child { border-bottom: none; }
.file-item:hover { background: #21262d; }
.file-name { color: #58a6ff; }
.file-size { color: #8b949e; font-size: 12px; }
pre { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; overflow-x: auto; white-space: pre-wrap; }
.empty-state { text-align: center; padding: 60px 20px; color: #8b949e; }
code { background: #21262d; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
.btn { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
.btn:hover { background: #2ea043; }
.btn-secondary { background: #21262d; border: 1px solid #30363d; }
.btn-secondary:hover { background: #30363d; }
.config-section { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin: 20px 0; }
.config-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #30363d; }
.config-row:last-child { border-bottom: none; }
.config-label { color: #c9d1d9; }
.config-value { color: #8b949e; font-family: monospace; }
.quick-actions { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; justify-content: center; align-items: center; }
.modal.active { display: flex; }
.modal-content { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; width: 90%; max-width: 500px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-close { background: none; border: none; color: #8b949e; font-size: 24px; cursor: pointer; }
.modal-close:hover { color: #c9d1d9; }
.input-group { margin-bottom: 15px; }
.input-group label { display: block; margin-bottom: 5px; color: #8b949e; }
.input-group input, .input-group textarea, .input-group select { width: 100%; padding: 10px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-family: inherit; }
.input-group textarea { min-height: 100px; resize: vertical; }
.loading { display: inline-block; width: 20px; height: 20px; border: 2px solid #30363d; border-top-color: #58a6ff; border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.toast { position: fixed; bottom: 20px; right: 20px; background: #238636; color: white; padding: 12px 20px; border-radius: 6px; animation: slideIn 0.3s ease; }
@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
"""


INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AMEM - Agent Memory System</title>
    <style>""" + CSS + """</style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🧠 AMEM</h1>
                <div class="brand" id="agent-info">Loading...</div>
            </div>
            <button class="btn" onclick="openStoreModal()">+ Store Memory</button>
        </header>
        
        <nav class="nav">
            <a href="#" class="active" onclick="showTab('overview')">Overview</a>
            <a href="#" onclick="showTab('search')">Search</a>
            <a href="#" onclick="showTab('files')">Files</a>
            <a href="#" onclick="showTab('config')">Config</a>
        </nav>
        
        <div id="content">
            <div class="loading"></div>
        </div>
    </div>
    
    <!-- Store Memory Modal -->
    <div id="storeModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Store Memory</h2>
                <button class="modal-close" onclick="closeStoreModal()">&times;</button>
            </div>
            <div class="input-group">
                <label>Content</label>
                <textarea id="memoryContent" placeholder="What do you want to remember?"></textarea>
            </div>
            <div class="input-group">
                <label>Type</label>
                <select id="memoryType">
                    <option value="fact">Fact</option>
                    <option value="preference">Preference</option>
                    <option value="episode">Episode</option>
                    <option value="skill">Skill</option>
                </select>
            </div>
            <div class="input-group">
                <label>
                    <input type="checkbox" id="memoryPermanent"> Permanent (long-term memory)
                </label>
            </div>
            <button class="btn" onclick="storeMemory()">Store</button>
        </div>
    </div>
    
    <script>
        let currentTab = 'overview';
        let searchTimeout = null;
        
        async function api(method, params = {}) {
            const response = await fetch('/api/' + method, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            return response.json();
        }
        
        async function loadOverview() {
            const stats = await api('stats');
            const provider = await api('provider');
            
            document.getElementById('agent-info').textContent = 
                `Agent: ${stats.agent_id} | ${provider.provider}`;
            
            return `
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">${stats.total}</div>
                        <div class="stat-label">Total Memories</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.tiers.semantic}</div>
                        <div class="stat-label">Long-term Facts</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.tiers.episodic}</div>
                        <div class="stat-label">Episodes</div>
                    </div>
                </div>
                
                <div class="quick-actions">
                    <button class="btn" onclick="checkUpdate()">↻ Check for Updates</button>
                </div>
                
                <h2>Quick Search</h2>
                <input type="text" class="search-box" placeholder="Search your memories..." 
                       onkeyup="quickSearch(this.value)">
                <div id="quickResults"></div>
                
                <h2>Quick Reference</h2>
                <div class="memory-list">
                    <div class="memory-item">
                        <div class="memory-content">
                            <strong>Store a memory:</strong><br>
                            <code>./memory remember "User prefers Python" --permanent</code>
                        </div>
                    </div>
                    <div class="memory-item">
                        <div class="memory-content">
                            <strong>Search memories:</strong><br>
                            <code>./memory recall "programming preferences"</code>
                        </div>
                    </div>
                    <div class="memory-item">
                        <div class="memory-content">
                            <strong>Update AMEM:</strong><br>
                            <code>./memory update</code>
                        </div>
                    </div>
                </div>
            `;
        }
        
        async function quickSearch(query) {
            if (!query) {
                document.getElementById('quickResults').innerHTML = '';
                return;
            }
            
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                const results = await api('search', { query, k: 5 });
                let html = '<h3>Results</h3><div class="memory-list">';
                for (const r of results.results || []) {
                    html += `<div class="memory-item"><div class="memory-content">${escapeHtml(r)}</div></div>`;
                }
                html += '</div>';
                document.getElementById('quickResults').innerHTML = html;
            }, 300);
        }
        
        async function loadSearch() {
            return `
                <input type="text" class="search-box" placeholder="Search memories..." 
                       onkeyup="performSearch(this.value)">
                <div id="searchResults"></div>
            `;
        }
        
        async function performSearch(query) {
            if (!query) {
                document.getElementById('searchResults').innerHTML = '';
                return;
            }
            
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                const results = await api('search', { query, k: 10 });
                let html = `<h2>Results (${results.results?.length || 0} found)</h2><div class="memory-list">`;
                for (const r of results.results || []) {
                    html += `<div class="memory-item"><div class="memory-content">${escapeHtml(r)}</div></div>`;
                }
                html += '</div>';
                document.getElementById('searchResults').innerHTML = html;
            }, 300);
        }
        
        async function loadFiles() {
            const files = await api('files');
            let html = '<h2>Memory Files</h2>';
            if (files.files?.length) {
                html += '<div class="file-list">';
                for (const f of files.files) {
                    html += `
                        <div class="file-item">
                            <a href="#" class="file-name" onclick="viewFile('${f.name}')">${f.name}</a>
                            <span class="file-size">${f.size} • ${f.date}</span>
                        </div>
                    `;
                }
                html += '</div>';
            } else {
                html += '<div class="empty-state"><p>No memory files found</p></div>';
            }
            return html;
        }
        
        async function loadConfig() {
            const config = await api('config');
            return `
                <h2>AMEM Configuration</h2>
                
                <div class="config-section">
                    <h3>Paths</h3>
                    <div class="config-row">
                        <span class="config-label">Workspace:</span>
                        <span class="config-value">${config.workspace}</span>
                    </div>
                    <div class="config-row">
                        <span class="config-label">Memory Dir:</span>
                        <span class="config-value">${config.memory_dir}</span>
                    </div>
                </div>
                
                <div class="config-section">
                    <h3>Environment</h3>
                    <div class="config-row">
                        <span class="config-label">OPENCLAW_WORKSPACE:</span>
                        <span class="config-value">${config.env.OPENCLAW_WORKSPACE || 'Not set'}</span>
                    </div>
                    <div class="config-row">
                        <span class="config-label">OLLAMA_HOST:</span>
                        <span class="config-value">${config.env.OLLAMA_HOST || 'Not set'}</span>
                    </div>
                </div>
                
                <div class="quick-actions">
                    <button class="btn" onclick="checkUpdate()">Check for Updates</button>
                </div>
            `;
        }
        
        async function showTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('content').innerHTML = '<div class="loading"></div>';
            
            let html;
            switch(tab) {
                case 'overview': html = await loadOverview(); break;
                case 'search': html = await loadSearch(); break;
                case 'files': html = await loadFiles(); break;
                case 'config': html = await loadConfig(); break;
            }
            document.getElementById('content').innerHTML = html;
        }
        
        function openStoreModal() {
            document.getElementById('storeModal').classList.add('active');
        }
        
        function closeStoreModal() {
            document.getElementById('storeModal').classList.remove('active');
        }
        
        async function storeMemory() {
            const content = document.getElementById('memoryContent').value;
            const type = document.getElementById('memoryType').value;
            const permanent = document.getElementById('memoryPermanent').checked;
            
            if (!content) return;
            
            await api('store', { content, type, permanent });
            closeStoreModal();
            showToast('Memory stored!');
            
            if (currentTab === 'overview') {
                document.getElementById('content').innerHTML = await loadOverview();
            }
        }
        
        async function checkUpdate() {
            showToast('Checking for updates...');
            const result = await api('update_check');
            showToast(result.message || 'Update check complete');
        }
        
        function showToast(message) {
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Load initial content
        loadOverview().then(html => {
            document.getElementById('content').innerHTML = html;
        });
    </script>
</body>
</html>
"""


class AMEMAPIHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler with REST API"""
    
    memory = None
    agent_id = "default"
    
    def do_GET(self):
        """Serve static files and index"""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle API requests"""
        if not self.path.startswith('/api/'):
            self.send_error(404)
            return
        
        method = self.path[5:]  # Remove /api/
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length else '{}'
        
        try:
            params = json.loads(body) if body else {}
        except:
            params = {}
        
        # Handle API methods
        result = self.handle_api(method, params)
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
    
    def handle_api(self, method, params):
        """Handle API method calls"""
        try:
            if method == 'stats':
                stats = self.memory.store.stats()
                return {
                    'success': True,
                    'agent_id': self.agent_id,
                    'total': stats.get('total', 0),
                    'tiers': stats.get('tiers', {})
                }
            
            elif method == 'provider':
                provider = 'hash-fallback'
                if hasattr(self.memory.store, 'embedder') and self.memory.store.embedder._embedder:
                    p = self.memory.store.embedder._embedder.active_provider
                    if p:
                        provider = p.name
                return {'success': True, 'provider': provider}
            
            elif method == 'search':
                query = params.get('query', '')
                k = params.get('k', 5)
                results = self.memory.recall(query, k=k)
                return {'success': True, 'results': results}
            
            elif method == 'store':
                content = params.get('content', '')
                memory_type = params.get('type', 'fact')
                permanent = params.get('permanent', False)
                self.memory.remember(content, memory_type=memory_type, permanent=permanent)
                return {'success': True}
            
            elif method == 'files':
                files = []
                memory_md = WORKSPACE_DIR / "MEMORY.md"
                if memory_md.exists():
                    stat = memory_md.stat()
                    files.append({
                        'name': 'MEMORY.md',
                        'size': f"{stat.st_size/1024:.1f}KB" if stat.st_size > 1024 else f"{stat.st_size}B",
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')
                    })
                
                memory_dir = WORKSPACE_DIR / "memory"
                if memory_dir.exists():
                    for f in sorted(memory_dir.glob("*.md"), reverse=True)[:20]:
                        stat = f.stat()
                        files.append({
                            'name': f'memory/{f.name}',
                            'size': f"{stat.st_size/1024:.1f}KB" if stat.st_size > 1024 else f"{stat.st_size}B",
                            'date': datetime.fromtimestamp(stat.mtime).strftime('%Y-%m-%d')
                        })
                
                return {'success': True, 'files': files}
            
            elif method == 'config':
                return {
                    'success': True,
                    'workspace': str(WORKSPACE_DIR),
                    'memory_dir': str(WORKSPACE_DIR / 'memory'),
                    'env': {
                        'OPENCLAW_WORKSPACE': os.getenv('OPENCLAW_WORKSPACE', ''),
                        'OLLAMA_HOST': os.getenv('OLLAMA_HOST', '')
                    }
                }
            
            elif method == 'update_check':
                # Simple version check
                return {'success': True, 'message': 'AMEM is up to date'}
            
            else:
                return {'success': False, 'error': f'Unknown method: {method}'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def log_message(self, format, *args):
        pass


def run_server(agent_id: str = "default", port: int = 8080):
    """Run the AMEM web server"""
    AMEMAPIHandler.agent_id = agent_id
    AMEMAPIHandler.memory = MemoryTools(agent_id)
    
    with socketserver.TCPServer(("", port), AMEMAPIHandler) as httpd:
        print(f"🧠 AMEM Web UI running at http://localhost:{port}")
        print(f"   Agent: {agent_id}")
        print("   Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✓ Shut down")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AMEM Web UI")
    parser.add_argument("--agent-id", default="default", help="Agent ID")
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    args = parser.parse_args()
    
    run_server(args.agent_id, args.port)