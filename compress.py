#!/usr/bin/env python3
"""
Memory Compression Service
Compresses old episodic memories into semantic summaries.
Reduces storage while preserving knowledge.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

import sys
NATIVE_DIR = Path(__file__).parent / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, MemoryTier, MemoryType


class MemoryCompressor:
    """
    Compresses old episodic memories into semantic summaries.
    """
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.memory = MemoryTools(agent_id)
        self.compression_log = []
    
    def find_compressible_memories(self, days_old: int = 30) -> List[Dict]:
        """Find old episodic memories that can be compressed"""
        from openclaw_memory import MEMORY_DIR
        
        compressible = []
        cutoff = datetime.now() - timedelta(days=days_old)
        
        # Find old daily log files
        if MEMORY_DIR.exists():
            for file in MEMORY_DIR.glob("*.md"):
                # Parse date from filename
                try:
                    date_str = file.stem
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if file_date < cutoff:
                        content = file.read_text()
                        compressible.append({
                            "file": str(file),
                            "date": date_str,
                            "content": content,
                            "size": len(content)
                        })
                except ValueError:
                    continue
        
        return sorted(compressible, key=lambda x: x["date"])
    
    def compress_daily_log(self, log_data: Dict) -> Optional[str]:
        """
        Compress a daily log into a semantic summary.
        Uses simple extraction - in production this would use an LLM.
        """
        content = log_data["content"]
        date = log_data["date"]
        
        # Extract key facts (lines that look like facts)
        lines = content.split('\n')
        facts = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Look for fact-like patterns
            if any(line.lower().startswith(p) for p in [
                'user', 'i ', 'we ', 'decided', 'learned', 'fixed', 'built', 'created'
            ]):
                facts.append(line)
        
        if not facts:
            return None
        
        # Create summary
        summary = f"## Summary for {date}\n\n"
        summary += f"Activities: {len(facts)} events recorded\n\n"
        summary += "Key points:\n"
        for fact in facts[:5]:  # Top 5 facts
            summary += f"- {fact}\n"
        
        return summary
    
    def compress_old_memories(self, days_old: int = 30, dry_run: bool = False) -> Dict:
        """
        Compress memories older than specified days.
        
        Args:
            days_old: Compress memories older than this many days
            dry_run: If True, don't actually modify files
        
        Returns:
            Compression statistics
        """
        print(f"Looking for memories older than {days_old} days...")
        
        old_logs = self.find_compressible_memories(days_old)
        
        if not old_logs:
            print("No old memories found to compress.")
            return {"compressed": 0, "bytes_saved": 0}
        
        print(f"Found {len(old_logs)} old daily logs")
        
        compressed_count = 0
        bytes_saved = 0
        summaries = []
        
        for log in old_logs:
            print(f"  Processing {log['date']}...")
            
            summary = self.compress_daily_log(log)
            
            if summary:
                summaries.append(summary)
                compressed_count += 1
                bytes_saved += log["size"]
                
                if not dry_run:
                    # Archive original (move to compressed folder)
                    compressed_dir = Path(log["file"]).parent / "compressed"
                    compressed_dir.mkdir(exist_ok=True)
                    
                    archive_path = compressed_dir / f"{log['date']}.md"
                    Path(log["file"]).rename(archive_path)
                    
                    print(f"    Archived to {archive_path}")
        
        # Store summaries to semantic memory
        if summaries and not dry_run:
            combined_summary = "\n".join(summaries)
            self.memory.remember(
                content=f"Compressed memory summaries:\n\n{combined_summary}",
                memory_type="episode",
                importance=0.6,
                permanent=True
            )
            print(f"  Stored combined summary to semantic memory")
        
        result = {
            "compressed": compressed_count,
            "bytes_saved": bytes_saved,
            "dry_run": dry_run
        }
        
        print(f"\nCompression complete:")
        print(f"  Files compressed: {compressed_count}")
        print(f"  Bytes saved: {bytes_saved}")
        
        return result
    
    def get_compression_stats(self) -> Dict:
        """Get statistics about compression"""
        from openclaw_memory import MEMORY_DIR
        
        stats = {
            "active_logs": 0,
            "compressed_logs": 0,
            "total_size_active": 0,
            "total_size_compressed": 0
        }
        
        if MEMORY_DIR.exists():
            # Count active logs
            for file in MEMORY_DIR.glob("*.md"):
                stats["active_logs"] += 1
                stats["total_size_active"] += file.stat().st_size
            
            # Count compressed
            compressed_dir = MEMORY_DIR / "compressed"
            if compressed_dir.exists():
                for file in compressed_dir.glob("*.md"):
                    stats["compressed_logs"] += 1
                    stats["total_size_compressed"] += file.stat().st_size
        
        return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Memory Compression Service")
    parser.add_argument("--agent", default="default", help="Agent ID")
    parser.add_argument("--days", type=int, default=30, help="Compress memories older than N days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be compressed without doing it")
    parser.add_argument("--stats", action="store_true", help="Show compression statistics")
    
    args = parser.parse_args()
    
    compressor = MemoryCompressor(args.agent)
    
    if args.stats:
        stats = compressor.get_compression_stats()
        print("Compression Statistics:")
        print(f"  Active logs: {stats['active_logs']}")
        print(f"  Compressed logs: {stats['compressed_logs']}")
        print(f"  Active size: {stats['total_size_active'] / 1024:.1f} KB")
        print(f"  Compressed size: {stats['total_size_compressed'] / 1024:.1f} KB")
    else:
        result = compressor.compress_old_memories(args.days, args.dry_run)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()