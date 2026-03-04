#!/usr/bin/env python3
"""
Memory Backup & Sync Service
Backup memories to git or export for migration.
"""
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent / "native"))

from openclaw_memory import WORKSPACE_DIR


class MemoryBackup:
    """Backup and sync memory files."""

    def __init__(self, workspace: Path = WORKSPACE_DIR):
        self.workspace = workspace
        self.backup_dir = workspace / "memory_backup"

    def export_to_json(self, output_file: str) -> dict:
        """Export all memories to JSON."""
        export = {
            "exported_at": datetime.now().isoformat(),
            "workspace": str(self.workspace),
            "memory_md": None,
            "daily_logs": {},
            "config": {}
        }

        # Export MEMORY.md
        memory_md = self.workspace / "MEMORY.md"
        if memory_md.exists():
            export["memory_md"] = memory_md.read_text()

        # Export daily logs
        memory_dir = self.workspace / "memory"
        if memory_dir.exists():
            for file in memory_dir.glob("*.md"):
                export["daily_logs"][file.name] = file.read_text()

        # Export config
        config_file = self.workspace / ".memory_config.json"
        if config_file.exists():
            with open(config_file) as f:
                export["config"] = json.load(f)

        # Write output
        with open(output_file, 'w') as f:
            json.dump(export, f, indent=2)

        return {
            "output": output_file,
            "memory_md_size": len(export["memory_md"] or ""),
            "daily_logs_count": len(export["daily_logs"])
        }

    def import_from_json(self, input_file: str, merge: bool = True) -> dict:
        """Import memories from JSON."""
        with open(input_file) as f:
            data = json.load(f)

        imported = {"memory_md": False, "daily_logs": 0}

        # Import MEMORY.md
        if data.get("memory_md"):
            memory_md = self.workspace / "MEMORY.md"
            if merge and memory_md.exists():
                existing = memory_md.read_text()
                memory_md.write_text(existing + "\n\n" + data["memory_md"])
            else:
                memory_md.write_text(data["memory_md"])
            imported["memory_md"] = True

        # Import daily logs
        memory_dir = self.workspace / "memory"
        memory_dir.mkdir(exist_ok=True)

        for filename, content in data.get("daily_logs", {}).items():
            file_path = memory_dir / filename
            if merge and file_path.exists():
                existing = file_path.read_text()
                file_path.write_text(existing + "\n" + content)
            else:
                file_path.write_text(content)
            imported["daily_logs"] += 1

        return imported

    def backup_to_git(self, remote_url: Optional[str] = None) -> dict:
        """Backup memories to a git repository."""
        backup_repo = self.backup_dir / "git"
        backup_repo.mkdir(parents=True, exist_ok=True)

        # Initialize git if needed
        git_dir = backup_repo / ".git"
        if not git_dir.exists():
            subprocess.run(["git", "init"], cwd=backup_repo, capture_output=True)

        # Copy memory files
        memory_md = self.workspace / "MEMORY.md"
        if memory_md.exists():
            shutil.copy2(memory_md, backup_repo / "MEMORY.md")

        memory_dir = self.workspace / "memory"
        if memory_dir.exists():
            backup_memory = backup_repo / "memory"
            backup_memory.mkdir(exist_ok=True)
            for file in memory_dir.glob("*.md"):
                shutil.copy2(file, backup_memory / file.name)

        # Commit
        subprocess.run(["git", "add", "."], cwd=backup_repo, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"Backup {datetime.now().isoformat()}"],
            cwd=backup_repo, capture_output=True
        )

        # Push if remote configured
        if remote_url:
            subprocess.run(
                ["git", "remote", "add", "origin", remote_url],
                cwd=backup_repo, capture_output=True
            )
            subprocess.run(["git", "push", "origin", "main"],
                          cwd=backup_repo, capture_output=True)

        return {
            "backup_dir": str(backup_repo),
            "committed": result.returncode == 0
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Memory Backup & Sync")
    parser.add_argument("command", choices=["export", "import", "git"])
    parser.add_argument("--file", "-f", help="File for export/import")
    parser.add_argument("--remote", help="Git remote URL")
    parser.add_argument("--merge", action="store_true", help="Merge on import")
    args = parser.parse_args()

    backup = MemoryBackup()

    if args.command == "export":
        result = backup.export_to_json(args.file or "memory_backup.json")
        print(f"Exported: {result}")
    elif args.command == "import":
        result = backup.import_from_json(args.file or "memory_backup.json", args.merge)
        print(f"Imported: {result}")
    elif args.command == "git":
        result = backup.backup_to_git(args.remote)
        print(f"Git backup: {result}")