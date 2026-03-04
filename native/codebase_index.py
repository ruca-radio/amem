#!/usr/bin/env python3
"""
Codebase Ingestion & Retrieval System
Efficiently indexes and retrieves code from large codebases.

Features:
- Incremental indexing (only changed files)
- Language-aware parsing
- Semantic code search
- Cross-reference tracking
- Efficient storage
"""
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import sys
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import WORKSPACE_DIR
from embeddings import MultiProviderEmbedding


@dataclass
class CodeSnippet:
    """A code snippet with metadata"""
    id: str
    file_path: str
    content: str
    language: str
    start_line: int
    end_line: int
    embedding: List[float] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    last_modified: float = 0.0


@dataclass
class FileIndex:
    """Index entry for a file"""
    path: str
    hash: str
    size: int
    modified: float
    language: str
    snippets: List[str] = field(default_factory=list)  # snippet IDs


class LanguageDetector:
    """Detect programming language from file extension"""
    
    EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".kt": "kotlin",
        ".scala": "scala",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".m": "objective-c",
        ".r": "r",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".ps1": "powershell",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".xml": "xml",
        ".md": "markdown",
        ".dockerfile": "dockerfile",
        ".tf": "terraform",
        ".proto": "protobuf",
    }
    
    @classmethod
    def detect(cls, file_path: Path) -> str:
        """Detect language from file path"""
        # Check for Dockerfile (no extension)
        if file_path.name.lower() == "dockerfile":
            return "dockerfile"
        
        # Check shebang for scripts without extension
        if file_path.suffix == "":
            try:
                with open(file_path) as f:
                    first_line = f.readline()
                    if first_line.startswith("#!/"):
                        if "python" in first_line:
                            return "python"
                        if "bash" in first_line or "sh" in first_line:
                            return "bash"
                        if "node" in first_line:
                            return "javascript"
                        if "ruby" in first_line:
                            return "ruby"
            except:
                pass
        
        return cls.EXTENSIONS.get(file_path.suffix.lower(), "unknown")


class CodeParser:
    """Parse code files into snippets"""
    
    def __init__(self):
        self.embedder = MultiProviderEmbedding()
    
    def parse_file(self, file_path: Path) -> List[CodeSnippet]:
        """Parse a file into semantic snippets"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except:
            return []
        
        language = LanguageDetector.detect(file_path)
        
        # Split into logical units based on language
        if language == "python":
            snippets = self._parse_python(content)
        elif language in ("javascript", "typescript"):
            snippets = self._parse_js_ts(content)
        else:
            # Generic: split by blank lines
            snippets = self._parse_generic(content)
        
        # Create snippet objects
        result = []
        for i, (start, end, text) in enumerate(snippets):
            snippet_id = hashlib.sha256(f"{file_path}:{start}:{end}".encode()).hexdigest()[:16]
            
            # Get embedding
            embedding = self.embedder.embed(text[:1000])  # Limit for speed
            
            snippet = CodeSnippet(
                id=snippet_id,
                file_path=str(file_path),
                content=text,
                language=language,
                start_line=start,
                end_line=end,
                embedding=embedding,
                symbols=self._extract_symbols(text, language),
                imports=self._extract_imports(text, language),
                last_modified=file_path.stat().st_mtime
            )
            result.append(snippet)
        
        return result
    
    def _parse_python(self, content: str) -> List[Tuple[int, int, str]]:
        """Parse Python into function/class definitions"""
        lines = content.split('\n')
        snippets = []
        
        pattern = re.compile(r'^(def |class |async def )')
        current_start = 0
        
        for i, line in enumerate(lines):
            if pattern.match(line):
                # Save previous snippet
                if i > current_start:
                    snippet_text = '\n'.join(lines[current_start:i]).strip()
                    if len(snippet_text) > 50:  # Min size
                        snippets.append((current_start + 1, i, snippet_text))
                current_start = i
        
        # Last snippet
        if current_start < len(lines):
            snippet_text = '\n'.join(lines[current_start:]).strip()
            if len(snippet_text) > 50:
                snippets.append((current_start + 1, len(lines), snippet_text))
        
        return snippets
    
    def _parse_js_ts(self, content: str) -> List[Tuple[int, int, str]]:
        """Parse JavaScript/TypeScript"""
        lines = content.split('\n')
        snippets = []
        
        pattern = re.compile(r'^(function |const |let |var |class |async function|export |import )')
        current_start = 0
        
        for i, line in enumerate(lines):
            if pattern.match(line):
                if i > current_start:
                    snippet_text = '\n'.join(lines[current_start:i]).strip()
                    if len(snippet_text) > 50:
                        snippets.append((current_start + 1, i, snippet_text))
                current_start = i
        
        if current_start < len(lines):
            snippet_text = '\n'.join(lines[current_start:]).strip()
            if len(snippet_text) > 50:
                snippets.append((current_start + 1, len(lines), snippet_text))
        
        return snippets
    
    def _parse_generic(self, content: str) -> List[Tuple[int, int, str]]:
        """Generic parsing by blank lines"""
        lines = content.split('\n')
        snippets = []
        current_start = 0
        
        for i, line in enumerate(lines):
            if line.strip() == "":
                if i > current_start:
                    snippet_text = '\n'.join(lines[current_start:i]).strip()
                    if len(snippet_text) > 100:
                        snippets.append((current_start + 1, i, snippet_text))
                current_start = i + 1
        
        # Last chunk
        if current_start < len(lines):
            snippet_text = '\n'.join(lines[current_start:]).strip()
            if len(snippet_text) > 100:
                snippets.append((current_start + 1, len(lines), snippet_text))
        
        return snippets
    
    def _extract_symbols(self, text: str, language: str) -> List[str]:
        """Extract function/class names"""
        symbols = []
        
        if language == "python":
            # Match def and class
            for match in re.finditer(r'^(def|class) (\w+)', text, re.MULTILINE):
                symbols.append(match.group(2))
        elif language in ("javascript", "typescript"):
            # Match function and class
            for match in re.finditer(r'function (\w+)|class (\w+)', text):
                symbols.append(match.group(1) or match.group(2))
        
        return symbols
    
    def _extract_imports(self, text: str, language: str) -> List[str]:
        """Extract import statements"""
        imports = []
        
        if language == "python":
            for match in re.finditer(r'^(import|from) (\S+)', text, re.MULTILINE):
                imports.append(match.group(2))
        elif language in ("javascript", "typescript"):
            for match in re.finditer(r'import .* from [\'"](.+)[\'"]', text):
                imports.append(match.group(1))
        
        return imports


class CodebaseIndex:
    """Index and search a codebase"""
    
    def __init__(self, project_path: Path, index_dir: Optional[Path] = None):
        self.project_path = Path(project_path).resolve()
        self.index_dir = index_dir or (WORKSPACE_DIR / "codebase_indices" / self.project_path.name)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        self.parser = CodeParser()
        self.files: Dict[str, FileIndex] = {}
        self.snippets: Dict[str, CodeSnippet] = {}
        
        self._load_index()
    
    def _load_index(self):
        """Load existing index"""
        index_file = self.index_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file) as f:
                    data = json.load(f)
                    for path, file_data in data.get("files", {}).items():
                        self.files[path] = FileIndex(**file_data)
            except:
                pass
        
        snippets_file = self.index_dir / "snippets.json"
        if snippets_file.exists():
            try:
                with open(snippets_file) as f:
                    data = json.load(f)
                    for sid, snippet_data in data.items():
                        self.snippets[sid] = CodeSnippet(**snippet_data)
            except:
                pass
    
    def _save_index(self):
        """Save index to disk"""
        index_file = self.index_dir / "index.json"
        with open(index_file, 'w') as f:
            json.dump({
                "project": str(self.project_path),
                "indexed_at": datetime.now().isoformat(),
                "files": {path: asdict(f) for path, f in self.files.items()}
            }, f, indent=2)
        
        snippets_file = self.index_dir / "snippets.json"
        with open(snippets_file, 'w') as f:
            json.dump({sid: asdict(s) for sid, s in self.snippets.items()}, f, indent=2)
    
    def index(self, incremental: bool = True):
        """Index the codebase"""
        print(f"Indexing {self.project_path}...")
        
        # Find all code files
        code_files = []
        for ext in LanguageDetector.EXTENSIONS.keys():
            code_files.extend(self.project_path.rglob(f"*{ext}"))
        
        # Add Dockerfiles
        code_files.extend(self.project_path.rglob("Dockerfile"))
        code_files.extend(self.project_path.rglob("dockerfile"))
        
        # Filter out common ignore patterns
        ignore_patterns = [
            r'node_modules',
            r'\.git',
            r'__pycache__',
            r'\.venv',
            r'venv',
            r'dist',
            r'build',
            r'\.tox',
            r'\.pytest_cache',
            r'\.mypy_cache'
        ]
        
        filtered_files = []
        for f in code_files:
            path_str = str(f)
            if not any(re.search(pattern, path_str) for pattern in ignore_patterns):
                filtered_files.append(f)
        
        print(f"Found {len(filtered_files)} code files")
        
        # Process files
        new_files = 0
        updated_files = 0
        
        for file_path in filtered_files:
            # Check if file needs re-indexing
            stat = file_path.stat()
            file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
            
            rel_path = str(file_path.relative_to(self.project_path))
            
            if incremental and rel_path in self.files:
                existing = self.files[rel_path]
                if existing.hash == file_hash:
                    continue  # Unchanged
                else:
                    # Remove old snippets
                    for sid in existing.snippets:
                        if sid in self.snippets:
                            del self.snippets[sid]
                    updated_files += 1
            else:
                new_files += 1
            
            # Parse file
            snippets = self.parser.parse_file(file_path)
            
            # Update index
            snippet_ids = [s.id for s in snippets]
            self.files[rel_path] = FileIndex(
                path=rel_path,
                hash=file_hash,
                size=stat.st_size,
                modified=stat.st_mtime,
                language=LanguageDetector.detect(file_path),
                snippets=snippet_ids
            )
            
            for snippet in snippets:
                self.snippets[snippet.id] = snippet
        
        # Save index
        self._save_index()
        
        print(f"Indexed: {new_files} new, {updated_files} updated")
        print(f"Total snippets: {len(self.snippets)}")
    
    def search(self, query: str, language: Optional[str] = None, k: int = 10) -> List[CodeSnippet]:
        """Semantic search over codebase"""
        query_embedding = self.parser.embedder.embed(query)
        
        # Score all snippets
        scored = []
        for snippet in self.snippets.values():
            # Filter by language
            if language and snippet.language != language:
                continue
            
            # Calculate similarity
            similarity = self._cosine_sim(query_embedding, snippet.embedding)
            
            # Boost for symbol matches
            for symbol in snippet.symbols:
                if symbol.lower() in query.lower():
                    similarity += 0.1
            
            scored.append((snippet, similarity))
        
        # Sort and return top k
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:k]]
    
    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity"""
        import math
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(x*x for x in b))
        return dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
    
    def find_definition(self, symbol: str) -> Optional[CodeSnippet]:
        """Find where a symbol is defined"""
        for snippet in self.snippets.values():
            if symbol in snippet.symbols:
                return snippet
        return None
    
    def get_stats(self) -> Dict:
        """Get index statistics"""
        languages = defaultdict(int)
        for snippet in self.snippets.values():
            languages[snippet.language] += 1
        
        return {
            "project": str(self.project_path),
            "files_indexed": len(self.files),
            "snippets_indexed": len(self.snippets),
            "languages": dict(languages),
            "index_size_mb": sum(
                (self.index_dir / f).stat().st_size 
                for f in ["index.json", "snippets.json"] 
                if (self.index_dir / f).exists()
            ) / (1024 * 1024)
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Codebase Indexer")
    parser.add_argument("path", nargs="?", default=".", help="Project path")
    parser.add_argument("--index", action="store_true", help="Index the codebase")
    parser.add_argument("--search", help="Search query")
    parser.add_argument("--language", help="Filter by language")
    parser.add_argument("--stats", action="store_true", help="Show stats")
    parser.add_argument("--find", help="Find symbol definition")
    
    args = parser.parse_args()
    
    project_path = Path(args.path).resolve()
    indexer = CodebaseIndex(project_path)
    
    if args.index:
        indexer.index()
    elif args.search:
        results = indexer.search(args.search, language=args.language)
        print(f"\nSearch results for '{args.search}':\n")
        for i, snippet in enumerate(results, 1):
            print(f"{i}. {snippet.file_path}:{snippet.start_line}")
            print(f"   Language: {snippet.language}")
            print(f"   Preview: {snippet.content[:100]}...")
            print()
    elif args.find:
        result = indexer.find_definition(args.find)
        if result:
            print(f"Found {args.find} in {result.file_path}:{result.start_line}")
            print(f"\n{result.content}")
        else:
            print(f"Symbol '{args.find}' not found")
    elif args.stats:
        stats = indexer.get_stats()
        print(json.dumps(stats, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()