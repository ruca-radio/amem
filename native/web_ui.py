#!/usr/bin/env python3
"""
Web UI for OpenClaw Memory System
Simple HTTP server for browsing and searching memories.
"""
import json
import http.server
import socketserver
import urllib.parse
from pathlib import Path
from datetime import datetime
import sys

# Import memory system
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, WORKSPACE_DIR


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; line-height: 1.6; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
header { border-bottom: 1px solid #30363d; padding-bottom: 20px; margin-bottom: 30px; }
h1 { color: #58a6ff; font-size: 28px; }
h2 { color: #79c0ff; font-size: 20px; margin: 20px 0 10px; }
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
"""


def render_page(agent_id: str, content: str, active: str = "overview") -> str:
    """Render HTML page"""
    active_overview = "active" if active == "overview" else ""
    active_search = "active" if active == "search" else ""
    active_files = "active" if active == "files" else ""
    
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenClaw Memory System</title>
    <style>""" + CSS + """</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🧠 OpenClaw Memory System</h1>
            <p>Agent: <strong>""" + agent_id + """</strong></p>
        </header>
        <nav class="nav">
            <a href="/" class=""" + active_overview + """>Overview</a>
            <a href="/search" class=""" + active_search + """>Search</a>
            <a href="/files" class=""" + active_files + """>Files</a>
        </nav>
        """ + content + """
    </div>
</body>
</html>"""


class MemoryWebUI:
    """Web UI server for memory system"""
    
    def __init__(self, agent_id: str = "default", port: int = 8080):
        self.agent_id = agent_id
        self.port = port
        self.memory = MemoryTools(agent_id)
    
    def render_overview(self) -> str:
        """Render overview page"""
        stats = self.memory.store.stats()
        
        content = """
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">""" + str(stats.get("total", 0)) + """</div>
                <div class="stat-label">Total Memories</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">""" + str(stats.get("tiers", {}).get("semantic", 0)) + """</div>
                <div class="stat-label">Long-term Facts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">""" + str(stats.get("tiers", {}).get("episodic", 0)) + """</div>
                <div class="stat-label">Episodes</div>
            </div>
        </div>
        
        <h2>Quick Search</h2>
        <form method="GET" action="/search">
            <input type="text" name="q" class="search-box" placeholder="Search your memories...">
        </form>
        
        <h2>How to Use</h2>
        <div class="memory-list">
            <div class="memory-item">
                <div class="memory-content">
                    <strong>Store a memory:</strong><br>
                    <code>memory.remember("User prefers Python", permanent=True)</code>
                </div>
            </div>
            <div class="memory-item">
                <div class="memory-content">
                    <strong>Search memories:</strong><br>
                    <code>memory.recall("programming preferences")</code>
                </div>
            </div>
            <div class="memory-item">
                <div class="memory-content">
                    <strong>Get context for prompts:</strong><br>
                    <code>memory.context_for_prompt("how to respond")</code>
                </div>
            </div>
        </div>
        """
        
        return render_page(self.agent_id, content, "overview")
    
    def render_search(self, query: str = "") -> str:
        """Render search page"""
        content = """
        <form method="GET" action="/search">
            <input type="text" name="q" class="search-box" 
                   placeholder="Search memories..." value=""" + json.dumps(query) + """>
        </form>
        """
        
        if query:
            results = self.memory.recall(query)
            
            content += "<h2>Results (" + str(len(results)) + " found)</h2>"
            content += '<div class="memory-list">'
            
            for result in results:
                content += '<div class="memory-item"><div class="memory-content">' + result + '</div></div>'
            
            content += '</div>'
        else:
            content += '''
            <div class="empty-state">
                <p>Enter a search query to find memories</p>
            </div>
            '''
        
        return render_page(self.agent_id, content, "search")
    
    def render_files(self) -> str:
        """Render files list page"""
        content = "<h2>Memory Files</h2>"
        
        # List files
        files = []
        
        memory_md = WORKSPACE_DIR / "MEMORY.md"
        if memory_md.exists():
            stat = memory_md.stat()
            files.append(("MEMORY.md", stat.st_size, stat.st_mtime))
        
        memory_dir = WORKSPACE_DIR / "memory"
        if memory_dir.exists():
            for f in sorted(memory_dir.glob("*.md"), reverse=True):
                stat = f.stat()
                files.append(("memory/" + f.name, stat.st_size, stat.st_mtime))
        
        if files:
            content += '<div class="file-list">'
            for name, size, mtime in files:
                size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                content += '<div class="file-item">'
                content += '<a href="/file?path=' + name + '" class="file-name">' + name + '</a>'
                content += '<span class="file-size">' + size_str + ' • ' + date_str + '</span>'
                content += '</div>'
            content += '</div>'
        else:
            content += '<div class="empty-state"><p>No memory files found</p></div>'
        
        return render_page(self.agent_id, content, "files")
    
    def render_file(self, path: str) -> str:
        """Render file content page"""
        if path == "MEMORY.md":
            file_path = WORKSPACE_DIR / "MEMORY.md"
        elif path.startswith("memory/"):
            file_path = WORKSPACE_DIR / path
        else:
            file_path = WORKSPACE_DIR / path
        
        if not file_path.exists():
            return render_page(self.agent_id, '<div class="empty-state"><p>File not found</p></div>', "files")
        
        file_content = file_path.read_text()
        html = '<h2>' + path + '</h2><pre>' + file_content + '</pre>'
        
        return render_page(self.agent_id, html, "files")


class MemoryHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler"""
    
    ui = None
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        if path == "/":
            html = self.ui.render_overview()
        elif path == "/search":
            q = query.get("q", [""])[0]
            html = self.ui.render_search(q)
        elif path == "/files":
            html = self.ui.render_files()
        elif path == "/file":
            file_path = query.get("path", [""])[0]
            html = self.ui.render_file(file_path)
        else:
            self.send_error(404)
            return
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        """Suppress request logging"""
        pass


def run_server(agent_id: str = "default", port: int = 8080):
    """Run the web UI server"""
    ui = MemoryWebUI(agent_id, port)
    MemoryHTTPHandler.ui = ui
    
    with socketserver.TCPServer(("", port), MemoryHTTPHandler) as httpd:
        print(f"Memory Web UI running at http://localhost:{port}")
        print(f"Agent: {agent_id}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", default="default")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    
    run_server(args.agent_id, args.port)