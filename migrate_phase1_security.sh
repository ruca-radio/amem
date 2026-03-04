#!/bin/bash
# AMEM Migration - Phase 1: Security Hardening
# Run this script to apply all P0 security fixes to v1

set -e

echo "🔒 AMEM Security Hardening - Phase 1"
echo "====================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
AMEM_DIR="$WORKSPACE/memory-system"

echo "📁 Working directory: $AMEM_DIR"
cd "$AMEM_DIR"

# Step 1: Backup current state
echo ""
echo "📦 Step 1: Creating backup..."
BACKUP_DIR="$WORKSPACE/amem_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r native "$BACKUP_DIR/"
cp amem_server.py "$BACKUP_DIR/" 2>/dev/null || true
cp memory-api/main.py "$BACKUP_DIR/" 2>/dev/null || true
echo -e "${GREEN}✓ Backup created: $BACKUP_DIR${NC}"

# Step 2: Check if security patch exists
echo ""
echo "🔧 Step 2: Applying security patch..."
if [ ! -f "security_patch.py" ]; then
    echo -e "${RED}✗ security_patch.py not found${NC}"
    echo "Download it first: curl -O https://raw.githubusercontent.com/ruca-radio/amem/main/security_patch.py"
    exit 1
fi

# Step 3: Patch amem_server.py
echo ""
echo "🔧 Step 3: Patching amem_server.py..."

# Create patched version
cat > amem_server_patched.py << 'PATCH_EOF'
#!/usr/bin/env python3
"""
AMEM Server - SECURITY PATCHED VERSION
This is a patched version with P0 security fixes applied.
"""
import sys
import os

# Add security patch to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import security components
from security_patch import (
    SecurityManager, 
    InputValidator, 
    PathSecurity,
    SafeErrorHandler,
    AuthenticationError,
    AuthorizationError,
    ValidationError
)

# Import original server (we'll monkey-patch the handler)
from amem_server import (
    AMEMAPIHandler as OriginalHandler,
    AMEMRegistry,
    run_http,
    main as original_main,
    registry,
    websocket_clients
)

# Initialize security
security = SecurityManager()

class SecureAMEMAPIHandler(OriginalHandler):
    """Patched handler with security fixes"""
    
    def do_POST(self):
        """Handle POST with security checks"""
        import json
        import logging
        
        logger = logging.getLogger('amem')
        
        # Read and validate content length
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > InputValidator.MAX_CONTENT_LENGTH:
            SafeErrorHandler.handle_error(
                ValidationError(f"Content too large: {content_length}"),
                is_development=False
            )
            self.send_json({'error': 'Content too large'}, 413)
            return
        
        # Read body
        try:
            body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
            data = json.loads(body)
        except json.JSONDecodeError as e:
            status, response = SafeErrorHandler.handle_error(
                ValidationError(f"Invalid JSON: {e}"),
                is_development=False
            )
            self.send_json(response, status)
            return
        except Exception as e:
            status, response = SafeErrorHandler.handle_error(e, is_development=False)
            self.send_json(response, status)
            return
        
        # Extract and validate agent_id
        agent_id = data.get('agent_id', 'default')
        try:
            # This will raise ValidationError if invalid
            if not security._is_valid_agent_id(agent_id):
                raise ValidationError(f"Invalid agent_id format: {agent_id}")
        except ValidationError as e:
            status, response = SafeErrorHandler.handle_error(e, is_development=False)
            self.send_json(response, status)
            return
        
        # Check for API key in header or body
        api_key = self.headers.get('X-API-Key') or data.get('api_key', '')
        
        # In development mode without keys, allow through
        if not security.api_keys:
            logger.warning(f"Development mode - no API key required for {agent_id}")
        else:
            # Require API key
            if not api_key:
                self.send_json({
                    'error': 'Authentication required',
                    'code': 'AUTH_REQUIRED',
                    'message': 'Provide API key via X-API-Key header or api_key field'
                }, 401)
                return
            
            try:
                security.authenticate(agent_id, api_key)
            except AuthenticationError as e:
                status, response = SafeErrorHandler.handle_error(e, is_development=False)
                self.send_json(response, status)
                return
        
        # Validate requested agent_id matches authenticated (for private endpoints)
        requested_agent = data.get('requested_agent_id', agent_id)
        try:
            security.authorize(agent_id, requested_agent)
        except AuthorizationError as e:
            status, response = SafeErrorHandler.handle_error(e, is_development=False)
            self.send_json(response, status)
            return
        
        # Validate inputs based on endpoint
        path = self.path
        try:
            if path == '/api/remember':
                data['content'] = InputValidator.validate_content(data.get('content'))
                data['type'] = InputValidator.validate_memory_type(data.get('type', 'fact'))
                data['scope'] = InputValidator.validate_scope(data.get('scope', 'auto'))
                data['importance'] = InputValidator.validate_importance(data.get('importance', 0.5))
            
            elif path == '/api/recall':
                data['query'] = InputValidator.validate_query(data.get('query'))
                data['k'] = InputValidator.validate_k(data.get('k', 5))
            
            elif path == '/api/context':
                data['query'] = InputValidator.validate_query(data.get('query', ''))
            
        except ValidationError as e:
            status, response = SafeErrorHandler.handle_error(e, is_development=False)
            self.send_json(response, status)
            return
        
        # Call original handler with validated data
        # We need to temporarily replace self.rfile to pass validated data
        from io import BytesIO
        original_rfile = self.rfile
        self.rfile = BytesIO(json.dumps(data).encode())
        self.headers['Content-Length'] = str(len(json.dumps(data)))
        
        try:
            # Call parent method
            super().do_POST()
        except Exception as e:
            logger.exception("Error in handler")
            status, response = SafeErrorHandler.handle_error(e, is_development=False)
            self.send_json(response, status)
        finally:
            self.rfile = original_rfile

# Replace handler class
import amem_server
amem_server.AMEMAPIHandler = SecureAMEMAPIHandler

if __name__ == '__main__':
    print("🔒 AMEM Server (Security Patched)")
    print("=================================")
    
    if not security.api_keys:
        print("⚠️  WARNING: Running in DEVELOPMENT mode - no API keys configured")
        print("   Set AMEM_API_KEYS environment variable for production")
    else:
        print(f"✓ Loaded {len(security.api_keys)} API keys")
    
    print("")
    
    # Run original main
    import asyncio
    asyncio.run(original_main())
PATCH_EOF

echo -e "${GREEN}✓ Created amem_server_patched.py${NC}"

# Step 4: Create SQL injection fix for memory-api
echo ""
echo "🔧 Step 4: Creating SQL injection fixes..."

if [ -f "memory-api/main.py" ]; then
    # Create a patch file
    cat > memory-api/sql_injection_fix.py << 'SQL_FIX'
"""
SQL Injection Fixes for memory-api
Replace f-string interpolation with parameterized queries
"""

# BEFORE (vulnerable):
# agent_filter = f"AND agent_id = '{req.agent_id}'" if req.agent_id else ""
# session_boost = f"CASE WHEN session_id = '{req.session_id}' THEN 0.1 ELSE 0 END +"

# AFTER (safe):
# Use asyncpg's parameterized queries

async def safe_query_memories(conn, req):
    """Query memories with parameterized queries (safe from SQL injection)"""
    
    params = []
    where_clauses = ["agent_id = $1"]
    params.append(req.agent_id)
    
    if req.session_id:
        where_clauses.append("session_id = $2")
        params.append(req.session_id)
    
    query = f"""
        SELECT id, content, embedding, memory_type, importance, created_at
        FROM memories
        WHERE {' AND '.join(where_clauses)}
        ORDER BY embedding <=> ${len(params) + 1}
        LIMIT ${len(params) + 2}
    """
    params.extend([req.query_embedding, req.k])
    
    return await conn.fetch(query, *params)

SQL_FIX
    echo -e "${GREEN}✓ Created SQL injection fix guide${NC}"
else
    echo -e "${YELLOW}⚠ memory-api/main.py not found, skipping SQL fix${NC}"
fi

# Step 5: Create path traversal fix
echo ""
echo "🔧 Step 5: Creating path traversal fix..."

cat > path_traversal_fix.py << 'PATH_FIX'
"""
Path Traversal Fix for openclaw_memory.py
"""
from pathlib import Path
from security_patch import PathSecurity, WORKSPACE_DIR

def safe_memory_get(path: str) -> str:
    """Safely get memory file content"""
    # Validate path is within workspace
    safe_path = PathSecurity.safe_path(WORKSPACE_DIR, path)
    
    if not safe_path.exists():
        raise FileNotFoundError(f"Memory file not found: {path}")
    
    return safe_path.read_text(encoding='utf-8')

def safe_memory_write(path: str, content: str) -> None:
    """Safely write memory file"""
    safe_path = PathSecurity.safe_path(WORKSPACE_DIR, path)
    
    # Ensure parent directory exists
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Atomic write
    temp_path = safe_path.with_suffix('.tmp')
    temp_path.write_text(content, encoding='utf-8')
    temp_path.rename(safe_path)

PATH_FIX

echo -e "${GREEN}✓ Created path_traversal_fix.py${NC}"

# Step 6: Create test script
echo ""
echo "🧪 Step 6: Creating security test script..."

cat > test_security.py << 'TEST_EOF'
#!/usr/bin/env python3
"""Security tests for AMEM"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from security_patch import (
    SecurityManager,
    InputValidator,
    PathSecurity,
    AuthenticationError,
    AuthorizationError,
    ValidationError
)

def test_authentication():
    """Test API key authentication"""
    print("Testing authentication...")
    
    # Test with no keys (dev mode)
    security = SecurityManager({})
    assert security.authenticate("test", "any-key") == True
    print("  ✓ Dev mode allows any key")
    
    # Test with keys
    security = SecurityManager({"agent1": "secret123"})
    assert security.authenticate("agent1", "secret123") == True
    print("  ✓ Valid key accepted")
    
    try:
        security.authenticate("agent1", "wrong-key")
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError:
        print("  ✓ Invalid key rejected")
    
    try:
        security.authenticate("unknown", "secret123")
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError:
        print("  ✓ Unknown agent rejected")

def test_authorization():
    """Test agent isolation"""
    print("Testing authorization...")
    
    security = SecurityManager({})
    
    # Agent can access own resources
    assert security.authorize("agent1", "agent1") == True
    print("  ✓ Agent can access own resources")
    
    # Agent cannot access other's resources
    try:
        security.authorize("agent1", "agent2")
        assert False, "Should have raised AuthorizationError"
    except AuthorizationError:
        print("  ✓ Agent isolation enforced")

def test_input_validation():
    """Test input validation"""
    print("Testing input validation...")
    
    # Valid content
    content = InputValidator.validate_content("Hello, world!")
    assert content == "Hello, world!"
    print("  ✓ Valid content accepted")
    
    # Empty content
    try:
        InputValidator.validate_content("")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        print("  ✓ Empty content rejected")
    
    # Content too long
    try:
        InputValidator.validate_content("x" * (InputValidator.MAX_CONTENT_LENGTH + 1))
        assert False, "Should have raised ValidationError"
    except ValidationError:
        print("  ✓ Oversized content rejected")
    
    # Valid query
    query = InputValidator.validate_query("test query")
    assert query == "test query"
    print("  ✓ Valid query accepted")

def test_path_security():
    """Test path traversal protection"""
    print("Testing path security...")
    
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        
        # Valid path
        safe = PathSecurity.safe_path(base, "memory", "test.txt")
        assert safe == base / "memory" / "test.txt"
        print("  ✓ Valid path accepted")
        
        # Path traversal attempt
        try:
            PathSecurity.safe_path(base, "..", "..", "etc", "passwd")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            print("  ✓ Path traversal blocked")
        
        # Safe filename
        safe_name = PathSecurity.safe_filename("test.txt")
        assert safe_name == "test.txt"
        print("  ✓ Safe filename preserved")
        
        # Dangerous filename
        safe_name = PathSecurity.safe_filename("../../../etc/passwd")
        assert ".." not in safe_name
        print("  ✓ Dangerous filename sanitized")

def run_all_tests():
    """Run all security tests"""
    print("=" * 50)
    print("AMEM Security Tests")
    print("=" * 50)
    print()
    
    test_authentication()
    test_authorization()
    test_input_validation()
    test_path_security()
    
    print()
    print("=" * 50)
    print("✓ All security tests passed!")
    print("=" * 50)

if __name__ == '__main__':
    run_all_tests()
TEST_EOF

chmod +x test_security.py
echo -e "${GREEN}✓ Created test_security.py${NC}"

# Step 7: Run tests
echo ""
echo "🧪 Step 7: Running security tests..."
python3 test_security.py || {
    echo -e "${RED}✗ Security tests failed${NC}"
    exit 1
}

# Step 8: Create startup script
echo ""
echo "📝 Step 8: Creating startup script..."

cat > start_secure.sh << 'START_EOF'
#!/bin/bash
# Start AMEM with security patches

export AMEM_API_KEYS="${AMEM_API_KEYS:-}"
export AMEM_SECURE_MODE="1"

echo "🔒 Starting AMEM (Security Patched)"
echo "==================================="

if [ -z "$AMEM_API_KEYS" ]; then
    echo "⚠️  WARNING: No API keys set (development mode)"
    echo "   Set AMEM_API_KEYS for production"
else
    echo "✓ API keys configured"
fi

echo ""
python3 amem_server_patched.py "$@"
START_EOF

chmod +x start_secure.sh
echo -e "${GREEN}✓ Created start_secure.sh${NC}"

# Summary
echo ""
echo "====================================="
echo -e "${GREEN}✓ Phase 1 Complete!${NC}"
echo "====================================="
echo ""
echo "Files created:"
echo "  • amem_server_patched.py - Patched server with security fixes"
echo "  • memory-api/sql_injection_fix.py - SQL injection prevention guide"
echo "  • path_traversal_fix.py - Path traversal protection"
echo "  • test_security.py - Security test suite"
echo "  • start_secure.sh - Secure startup script"
echo ""
echo "Next steps:"
echo "  1. Set API keys: export AMEM_API_KEYS='agent1:key1,agent2:key2'"
echo "  2. Run tests: python3 test_security.py"
echo "  3. Start server: ./start_secure.sh"
echo "  4. Continue to Phase 2: Database setup"
echo ""
echo "Backup location: $BACKUP_DIR"

exit 0
