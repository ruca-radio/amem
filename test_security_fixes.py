#!/usr/bin/env python3
"""
Security Fix Tests for AMEM

Tests to verify:
1. API key authentication works
2. Input validation blocks invalid inputs
3. Path traversal is blocked
4. SQL injection is prevented
5. Safe error messages (no stack traces)
"""
import sys
import os
import unittest
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "native"))
sys.path.insert(0, str(Path(__file__).parent / "services" / "memory-api"))

from security_patch import (
    SecurityManager, InputValidator, PathSecurity, SafeErrorHandler,
    AuthenticationError, AuthorizationError, ValidationError
)


class TestAPIKeyAuthentication(unittest.TestCase):
    """Test API key authentication"""
    
    def setUp(self):
        self.security = SecurityManager({
            "test-agent": "test-key-12345",
            "admin": "admin-secret-key"
        })
    
    def test_valid_authentication(self):
        """Valid API key should authenticate"""
        result = self.security.authenticate("test-agent", "test-key-12345")
        self.assertTrue(result)
    
    def test_invalid_api_key(self):
        """Invalid API key should fail"""
        with self.assertRaises(AuthenticationError):
            self.security.authenticate("test-agent", "wrong-key")
    
    def test_unknown_agent(self):
        """Unknown agent should fail"""
        with self.assertRaises(AuthenticationError):
            self.security.authenticate("unknown-agent", "some-key")
    
    def test_invalid_agent_id_format(self):
        """Invalid agent_id format should fail"""
        with self.assertRaises(AuthenticationError):
            self.security.authenticate("../etc/passwd", "test-key-12345")
        
        with self.assertRaises(AuthenticationError):
            self.security.authenticate("agent;rm -rf /", "test-key-12345")
    
    def test_timing_attack_protection(self):
        """Authentication should use constant-time comparison"""
        # This test just verifies the function doesn't throw
        result = self.security.authenticate("test-agent", "test-key-12345")
        self.assertTrue(result)


class TestInputValidation(unittest.TestCase):
    """Test input validation"""
    
    def test_valid_content(self):
        """Valid content should pass"""
        result = InputValidator.validate_content("Hello, world!")
        self.assertEqual(result, "Hello, world!")
    
    def test_empty_content(self):
        """Empty content should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_content("")
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_content("   ")
    
    def test_non_string_content(self):
        """Non-string content should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_content(123)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_content(None)
    
    def test_content_too_long(self):
        """Content exceeding max length should fail"""
        long_content = "x" * (InputValidator.MAX_CONTENT_LENGTH + 1)
        with self.assertRaises(ValidationError):
            InputValidator.validate_content(long_content)
    
    def test_valid_query(self):
        """Valid query should pass"""
        result = InputValidator.validate_query("search query")
        self.assertEqual(result, "search query")
    
    def test_empty_query(self):
        """Empty query should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_query("")
    
    def test_query_too_long(self):
        """Query exceeding max length should fail"""
        long_query = "x" * (InputValidator.MAX_QUERY_LENGTH + 1)
        with self.assertRaises(ValidationError):
            InputValidator.validate_query(long_query)
    
    def test_valid_memory_type(self):
        """Valid memory type should pass"""
        result = InputValidator.validate_memory_type("fact")
        self.assertEqual(result, "fact")
    
    def test_invalid_memory_type(self):
        """Invalid memory type should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_memory_type("invalid_type")
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_memory_type("'; DROP TABLE memories; --")
    
    def test_valid_scope(self):
        """Valid scope should pass"""
        result = InputValidator.validate_scope("shared")
        self.assertEqual(result, "shared")
    
    def test_invalid_scope(self):
        """Invalid scope should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_scope("invalid_scope")
    
    def test_valid_importance(self):
        """Valid importance should pass"""
        result = InputValidator.validate_importance(0.5)
        self.assertEqual(result, 0.5)
        
        result = InputValidator.validate_importance("0.7")
        self.assertEqual(result, 0.7)
    
    def test_invalid_importance(self):
        """Invalid importance should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_importance(1.5)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_importance(-0.1)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_importance("not-a-number")
    
    def test_valid_k(self):
        """Valid k should pass"""
        result = InputValidator.validate_k(10)
        self.assertEqual(result, 10)
    
    def test_invalid_k(self):
        """Invalid k should fail"""
        with self.assertRaises(ValidationError):
            InputValidator.validate_k(0)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_k(-5)
        
        with self.assertRaises(ValidationError):
            InputValidator.validate_k(1000)
    
    def test_injection_pattern_detection(self):
        """Injection patterns should be detected"""
        # These should be detected (returns True)
        self.assertTrue(InputValidator._has_injection_patterns("${SHELL}"))
        self.assertTrue(InputValidator._has_injection_patterns("`rm -rf /`"))
        self.assertTrue(InputValidator._has_injection_patterns("SELECT * FROM users"))
        self.assertTrue(InputValidator._has_injection_patterns("../etc/passwd"))
        
        # These should be safe (returns False)
        self.assertFalse(InputValidator._has_injection_patterns("Hello world"))
        self.assertFalse(InputValidator._has_injection_patterns("User prefers dark mode"))


class TestPathTraversalProtection(unittest.TestCase):
    """Test path traversal protection"""
    
    def setUp(self):
        self.base_dir = Path("/tmp/test_amem")
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def tearDown(self):
        # Cleanup
        import shutil
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
    
    def test_safe_path_construction(self):
        """Safe path should be constructed correctly"""
        path = PathSecurity.safe_path(self.base_dir, "memory", "test.txt")
        self.assertTrue(path.is_relative_to(self.base_dir))
    
    def test_path_traversal_blocked(self):
        """Path traversal attempts should be blocked"""
        with self.assertRaises(ValidationError):
            PathSecurity.safe_path(self.base_dir, "..", "etc", "passwd")
        
        with self.assertRaises(ValidationError):
            PathSecurity.safe_path(self.base_dir, "memory", "../../etc/passwd")
    
    def test_safe_filename(self):
        """Filename should be sanitized"""
        # Path separators should be replaced
        result = PathSecurity.safe_filename("../etc/passwd")
        # Leading dots are stripped for security
        self.assertEqual(result, "_etc_passwd")
        
        result = PathSecurity.safe_filename("test\\file.txt")
        self.assertEqual(result, "test_file.txt")
        
        # Null bytes should be removed
        result = PathSecurity.safe_filename("file\x00.txt")
        self.assertEqual(result, "file.txt")
        
        # Leading dots should be removed
        result = PathSecurity.safe_filename(".hidden")
        self.assertEqual(result, "hidden")
        
        # Empty filename should default
        result = PathSecurity.safe_filename("")
        self.assertEqual(result, "unnamed")


class TestSafeErrorHandling(unittest.TestCase):
    """Test safe error handling"""
    
    def test_authentication_error(self):
        """Authentication error should return safe response"""
        error = AuthenticationError("Invalid credentials")
        status, response = SafeErrorHandler.handle_error(error)
        
        self.assertEqual(status, 401)
        self.assertEqual(response['code'], 'AUTH_FAILED')
        self.assertNotIn('Invalid credentials', response['error'])
    
    def test_authorization_error(self):
        """Authorization error should return safe response"""
        error = AuthorizationError("Access denied")
        status, response = SafeErrorHandler.handle_error(error)
        
        self.assertEqual(status, 403)
        self.assertEqual(response['code'], 'ACCESS_DENIED')
    
    def test_validation_error(self):
        """Validation error can include details"""
        error = ValidationError("Invalid field: name")
        status, response = SafeErrorHandler.handle_error(error)
        
        self.assertEqual(status, 400)
        self.assertEqual(response['code'], 'VALIDATION_ERROR')
        self.assertIn('Invalid field', response['error'])
    
    def test_internal_error_production(self):
        """Internal error in production should not leak details"""
        error = Exception("Database connection failed: password=secret123")
        status, response = SafeErrorHandler.handle_error(error, is_development=False)
        
        self.assertEqual(status, 500)
        self.assertEqual(response['code'], 'INTERNAL_ERROR')
        self.assertNotIn('password', response['error'])
        self.assertNotIn('secret123', str(response))
    
    def test_internal_error_development(self):
        """Internal error in development can include details"""
        error = Exception("Database connection failed")
        status, response = SafeErrorHandler.handle_error(error, is_development=True)
        
        self.assertEqual(status, 500)
        self.assertEqual(response['code'], 'INTERNAL_ERROR')
        self.assertIn('detail', response)


class TestAgentIDValidation(unittest.TestCase):
    """Test agent_id format validation"""
    
    def test_valid_agent_ids(self):
        """Valid agent IDs should pass"""
        security = SecurityManager()
        
        self.assertTrue(security._is_valid_agent_id("agent1"))
        self.assertTrue(security._is_valid_agent_id("my-agent"))
        self.assertTrue(security._is_valid_agent_id("my_agent"))
        self.assertTrue(security._is_valid_agent_id("agent123"))
        self.assertTrue(security._is_valid_agent_id("a"))
    
    def test_invalid_agent_ids(self):
        """Invalid agent IDs should fail"""
        security = SecurityManager()
        
        # Path traversal
        self.assertFalse(security._is_valid_agent_id("../etc/passwd"))
        self.assertFalse(security._is_valid_agent_id(".."))
        
        # SQL injection
        self.assertFalse(security._is_valid_agent_id("'; DROP TABLE users; --"))
        
        # Command injection
        self.assertFalse(security._is_valid_agent_id("agent; rm -rf /"))
        
        # Empty or too long
        self.assertFalse(security._is_valid_agent_id(""))
        self.assertFalse(security._is_valid_agent_id("a" * 65))
        
        # Special characters
        self.assertFalse(security._is_valid_agent_id("agent@domain"))
        self.assertFalse(security._is_valid_agent_id("agent.name"))
        self.assertFalse(security._is_valid_agent_id("agent/name"))


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def test_full_authentication_flow(self):
        """Test full authentication flow"""
        security = SecurityManager({
            "test-agent": "secret-key"
        })
        
        # Valid authentication
        self.assertTrue(security.authenticate("test-agent", "secret-key"))
        
        # Invalid authentication
        with self.assertRaises(AuthenticationError):
            security.authenticate("test-agent", "wrong-key")
        
        # Invalid agent_id
        with self.assertRaises(AuthenticationError):
            security.authenticate("../etc/passwd", "secret-key")
    
    def test_input_validation_chain(self):
        """Test input validation in sequence"""
        # Valid inputs
        content = InputValidator.validate_content("Valid memory content")
        query = InputValidator.validate_query("search term")
        memory_type = InputValidator.validate_memory_type("fact")
        importance = InputValidator.validate_importance(0.8)
        k = InputValidator.validate_k(10)
        
        self.assertEqual(content, "Valid memory content")
        self.assertEqual(query, "search term")
        self.assertEqual(memory_type, "fact")
        self.assertEqual(importance, 0.8)
        self.assertEqual(k, 10)


def run_tests():
    """Run all security tests"""
    print("=" * 60)
    print("AMEM Security Fix Tests")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAPIKeyAuthentication))
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestPathTraversalProtection))
    suite.addTests(loader.loadTestsFromTestCase(TestSafeErrorHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentIDValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✓ All security tests passed!")
    else:
        print("✗ Some tests failed!")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
