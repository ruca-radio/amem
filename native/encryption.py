#!/usr/bin/env python3
"""
Memory Encryption - Optional encryption for sensitive memories
Uses Fernet symmetric encryption from cryptography library
"""
import json
import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Optional import - system works without encryption if not available
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class MemoryEncryption:
    """
    Optional encryption for sensitive memory entries.
    Falls back to plaintext if cryptography not installed.
    """
    
    def __init__(self, key: Optional[bytes] = None, password: Optional[str] = None):
        self._fernet = None
        self._enabled = False
        
        if not HAS_CRYPTO:
            print("[Encryption] cryptography not installed, encryption disabled")
            print("[Encryption] Install with: pip install cryptography")
            return
        
        if key:
            self._fernet = Fernet(key)
            self._enabled = True
        elif password:
            self._derive_key(password)
            self._enabled = True
    
    def _derive_key(self, password: str, salt: Optional[bytes] = None):
        """Derive encryption key from password"""
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self._fernet = Fernet(key)
        return salt
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data"""
        if not self._enabled or not self._fernet:
            # Return plaintext marker + data
            return f"PLAINTEXT:{data}"
        
        encrypted = self._fernet.encrypt(data.encode())
        return f"ENCRYPTED:{encrypted.decode()}"
    
    def decrypt(self, data: str) -> Optional[str]:
        """Decrypt string data"""
        if data.startswith("PLAINTEXT:"):
            return data[10:]
        
        if data.startswith("ENCRYPTED:"):
            if not self._enabled or not self._fernet:
                return "[ENCRYPTED - key required]"
            
            try:
                encrypted = data[10:].encode()
                decrypted = self._fernet.decrypt(encrypted)
                return decrypted.decode()
            except Exception as e:
                return f"[DECRYPTION FAILED: {e}]"
        
        # Legacy: assume plaintext
        return data
    
    def is_enabled(self) -> bool:
        """Check if encryption is enabled"""
        return self._enabled
    
    @staticmethod
    def generate_key() -> bytes:
        """Generate a new encryption key"""
        if not HAS_CRYPTO:
            raise ImportError("cryptography library required")
        return Fernet.generate_key()


class EncryptedMemoryStore:
    """Wrapper that adds encryption to memory operations"""
    
    def __init__(self, base_store, encryption: Optional[MemoryEncryption] = None):
        self.store = base_store
        self.encryption = encryption or MemoryEncryption()
    
    def store_encrypted(self, content: str, **kwargs) -> Any:
        """Store memory with encryption"""
        if self.encryption.is_enabled():
            content = self.encryption.encrypt(content)
        return self.store.store(content, **kwargs)
    
    def get_decrypted(self, memory_id: str) -> Optional[str]:
        """Get memory and decrypt if needed"""
        # This would need integration with the actual store
        # For now, just a placeholder
        pass


def setup_encryption(workspace: Path, password: Optional[str] = None) -> MemoryEncryption:
    """Setup encryption for a workspace"""
    key_file = workspace / ".memory_key"
    
    if key_file.exists():
        # Load existing key
        key = key_file.read_bytes()
        return MemoryEncryption(key=key)
    
    if password:
        # Create new encryption from password
        encryption = MemoryEncryption(password=password)
        # Save key for future use
        if encryption.is_enabled():
            # Note: In production, you'd want to protect this key better
            key_file.write_bytes(encryption._fernet._encryption_key)
        return encryption
    
    # No encryption
    return MemoryEncryption()


if __name__ == "__main__":
    # Demo
    print("Memory Encryption Demo")
    print("=" * 50)
    
    if not HAS_CRYPTO:
        print("cryptography not installed. Install with: pip install cryptography")
        sys.exit(1)
    
    # Generate key
    key = MemoryEncryption.generate_key()
    print(f"Generated key: {key.decode()}")
    
    # Create encryption
    enc = MemoryEncryption(key=key)
    
    # Test encrypt/decrypt
    message = "User's secret API key: sk-123456789"
    print(f"\nOriginal: {message}")
    
    encrypted = enc.encrypt(message)
    print(f"Encrypted: {encrypted}")
    
    decrypted = enc.decrypt(encrypted)
    print(f"Decrypted: {decrypted}")
    
    # Test without key
    enc2 = MemoryEncryption()
    print(f"\nWithout key: {enc2.decrypt(encrypted)}")