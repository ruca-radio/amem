#!/usr/bin/env python3
"""
Self-Update Script for OpenClaw Memory System
Agents can run this to update their memory system installation.

Usage:
    python3 update.py [--check] [--force] [--backup]

Features:
- Checks for updates from GitHub
- Creates backup before updating
- Preserves user data and config
- Reports what changed
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

# Configuration
REPO_URL = "https://github.com/ruca-radio/amem"
RAW_URL = "https://raw.githubusercontent.com/ruca-radio/amem/main"
VERSION_FILE = ".memory_version"

# Get workspace from environment or default
WORKSPACE = Path(os.getenv("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
MEMORY_SYSTEM_DIR = WORKSPACE / "memory_system"


def get_local_version() -> str:
    """Get currently installed version"""
    version_file = MEMORY_SYSTEM_DIR / VERSION_FILE
    if version_file.exists():
        return version_file.read_text().strip()
    # Fallback: check if installed
    if MEMORY_SYSTEM_DIR.exists():
        return "installed"
    return "not-installed"


def get_remote_version() -> str:
    """Get latest version from GitHub"""
    try:
        # Get latest commit SHA
        url = f"{RAW_URL}/.memory_version"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode().strip()
    except:
        # Fallback: check a key file
        try:
            url = f"{RAW_URL}/native/openclaw_memory.py"
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                # Use etag or last-modified as version proxy
                return resp.headers.get('ETag', 'unknown').strip('"')
        except:
            return "unknown"


def check_for_updates() -> dict:
    """Check if updates are available"""
    local = get_local_version()
    remote = get_remote_version()
    
    return {
        "local_version": local,
        "remote_version": remote,
        "update_available": local != remote and remote != "unknown",
        "current_time": datetime.now().isoformat()
    }


def create_backup() -> Path:
    """Create backup of current installation"""
    if not MEMORY_SYSTEM_DIR.exists():
        return None
    
    backup_dir = WORKSPACE / f"memory_system_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copytree(MEMORY_SYSTEM_DIR, backup_dir)
    return backup_dir


def download_file(url: str, dest: Path) -> bool:
    """Download a file from GitHub"""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  ✗ Failed to download {url}: {e}")
        return False


def update_files() -> dict:
    """Update all files from GitHub"""
    files_to_update = [
        "native/openclaw_memory.py",
        "native/embeddings.py",
        "native/auto_extract.py",
        "native/graph_memory.py",
        "native/web_ui.py",
        "native/memory_tool.py",
        "native/encryption.py",
        "install.py",
        "memory",
        "compress.py",
        "test_memory.py",
        "README.md",
    ]
    
    results = {
        "updated": [],
        "failed": [],
        "skipped": []
    }
    
    print("Downloading updates...")
    
    for file in files_to_update:
        url = f"{RAW_URL}/{file}"
        dest = MEMORY_SYSTEM_DIR.parent / file
        
        # Check if file exists locally
        if dest.exists():
            # Download to temp first
            temp_file = Path(tempfile.gettempdir()) / f"amem_update_{file.replace('/', '_')}"
            
            if download_file(url, temp_file):
                # Compare with existing
                existing = dest.read_bytes()
                new = temp_file.read_bytes()
                
                if existing != new:
                    # Backup old file
                    backup = dest.with_suffix(dest.suffix + ".old")
                    shutil.copy2(dest, backup)
                    
                    # Replace with new
                    shutil.copy2(temp_file, dest)
                    results["updated"].append(file)
                    print(f"  ✓ Updated: {file}")
                else:
                    results["skipped"].append(file)
                
                # Clean up temp
                temp_file.unlink()
            else:
                results["failed"].append(file)
        else:
            # New file
            if download_file(url, dest):
                results["updated"].append(file)
                print(f"  ✓ New file: {file}")
            else:
                results["failed"].append(file)
    
    return results


def update_version_file():
    """Update version tracking file"""
    version_file = MEMORY_SYSTEM_DIR / VERSION_FILE
    remote = get_remote_version()
    version_file.write_text(remote)


def run_tests() -> bool:
    """Run test suite to verify update"""
    print("\nRunning tests...")
    test_file = MEMORY_SYSTEM_DIR.parent / "test_memory.py"
    
    if test_file.exists():
        result = subprocess.run(
            [sys.executable, str(test_file)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("  ✓ All tests passed")
            return True
        else:
            print("  ✗ Tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
    else:
        print("  ⚠ No tests found")
        return True


def restore_backup(backup_dir: Path):
    """Restore from backup if update fails"""
    print(f"\nRestoring from backup: {backup_dir}")
    
    if MEMORY_SYSTEM_DIR.exists():
        shutil.rmtree(MEMORY_SYSTEM_DIR)
    
    shutil.copytree(backup_dir, MEMORY_SYSTEM_DIR)
    print("  ✓ Backup restored")


def main():
    parser = argparse.ArgumentParser(
        description="Update OpenClaw Memory System"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check for updates, don't install"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update even if no changes detected"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup"
    )
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip running tests after update"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("OpenClaw Memory System - Self-Update")
    print("=" * 60)
    print(f"Workspace: {WORKSPACE}")
    print(f"Repository: {REPO_URL}")
    print("-" * 60)
    
    # Check for updates
    print("\nChecking for updates...")
    status = check_for_updates()
    
    print(f"  Local version:  {status['local_version']}")
    print(f"  Remote version: {status['remote_version']}")
    
    if args.check:
        if status['update_available']:
            print("\n✓ Update available!")
            print(f"  Run without --check to install")
        else:
            print("\n✓ Already up to date")
        return 0
    
    if not status['update_available'] and not args.force:
        print("\n✓ Already up to date (use --force to update anyway)")
        return 0
    
    # Confirm update
    if not args.force:
        response = input("\nInstall update? [Y/n]: ").strip().lower()
        if response and response not in ('y', 'yes'):
            print("Update cancelled")
            return 0
    
    # Create backup
    backup_dir = None
    if not args.no_backup:
        print("\nCreating backup...")
        backup_dir = create_backup()
        if backup_dir:
            print(f"  ✓ Backup created: {backup_dir}")
        else:
            print("  ⚠ Nothing to backup (fresh install)")
    
    # Perform update
    print("\nUpdating files...")
    results = update_files()
    
    print(f"\nUpdate summary:")
    print(f"  Updated: {len(results['updated'])} files")
    print(f"  Skipped: {len(results['skipped'])} files (unchanged)")
    print(f"  Failed:  {len(results['failed'])} files")
    
    if results['failed']:
        print("\n✗ Some files failed to update")
        if backup_dir:
            restore_backup(backup_dir)
        return 1
    
    # Update version file
    update_version_file()
    
    # Run tests
    if not args.no_tests:
        if not run_tests():
            print("\n✗ Tests failed after update")
            if backup_dir:
                restore_backup(backup_dir)
            return 1
    
    # Success
    print("\n" + "=" * 60)
    print("✓ Update complete!")
    print(f"  Version: {get_remote_version()}")
    if backup_dir:
        print(f"  Backup:  {backup_dir}")
    print("\nRestart your agent to use the updated memory system")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())