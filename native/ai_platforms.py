#!/usr/bin/env python3
"""
AI Code Platform Integration for OpenClaw Memory System
Integrates with Claude Code, OpenCode, and other AI code gen platforms.

Supports:
- Claude Code (via context files)
- OpenCode (via workspace memory)
- Cursor (via .cursorrules)
- GitHub Copilot (via prompts)
- Generic (via standard formats)
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import sys
NATIVE_DIR = Path(__file__).parent / "native"
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, WORKSPACE_DIR


@dataclass
class CodeContext:
    """Structured context for AI code platforms"""
    project_name: str
    description: str
    tech_stack: List[str]
    conventions: List[str]
    patterns: List[str]
    avoid: List[str]
    examples: List[Dict[str, str]]
    memories: List[str]
    
    def to_claude_code(self) -> str:
        """Format for Claude Code CLAUDE.md"""
        sections = [
            f"# {self.project_name}",
            "",
            self.description,
            "",
            "## Tech Stack",
            "",
        ]
        for tech in self.tech_stack:
            sections.append(f"- {tech}")
        
        sections.extend(["", "## Conventions", ""])
        for conv in self.conventions:
            sections.append(f"- {conv}")
        
        sections.extend(["", "## Patterns", ""])
        for pattern in self.patterns:
            sections.append(f"- {pattern}")
        
        sections.extend(["", "## Avoid", ""])
        for item in self.avoid:
            sections.append(f"- {item}")
        
        if self.examples:
            sections.extend(["", "## Examples", ""])
            for ex in self.examples:
                sections.append(f"### {ex.get('name', 'Example')}")
                sections.append(f"```")
                sections.append(ex.get('code', ''))
                sections.append(f"```")
                sections.append("")
        
        if self.memories:
            sections.extend(["", "## Project Memory", ""])
            for mem in self.memories[:10]:  # Limit to 10
                sections.append(f"- {mem}")
        
        return "\n".join(sections)
    
    def to_opencode(self) -> Dict[str, Any]:
        """Format for OpenCode workspace memory"""
        return {
            "project": {
                "name": self.project_name,
                "description": self.description,
                "tech_stack": self.tech_stack
            },
            "conventions": self.conventions,
            "patterns": self.patterns,
            "avoid": self.avoid,
            "examples": self.examples,
            "context": self.memories[:20]  # OpenCode can handle more
        }
    
    def to_cursor(self) -> str:
        """Format for Cursor .cursorrules"""
        lines = [
            f"# {self.project_name}",
            "",
            self.description,
            "",
            "## Rules",
            "",
        ]
        
        for conv in self.conventions:
            lines.append(f"- {conv}")
        
        for pattern in self.patterns:
            lines.append(f"- {pattern}")
        
        lines.extend(["", "## Avoid", ""])
        for item in self.avoid:
            lines.append(f"- NEVER: {item}")
        
        return "\n".join(lines)
    
    def to_copilot(self) -> str:
        """Format for GitHub Copilot custom instructions"""
        lines = [
            f"You are working on {self.project_name}.",
            "",
            f"Description: {self.description}",
            "",
            f"Tech stack: {', '.join(self.tech_stack)}",
            "",
            "Conventions:",
        ]
        for conv in self.conventions:
            lines.append(f"- {conv}")
        
        lines.extend(["", "Key patterns:"])
        for pattern in self.patterns:
            lines.append(f"- {pattern}")
        
        return "\n".join(lines)


class AIPlatformIntegration:
    """Integrate memory system with AI code platforms"""
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.memory = MemoryTools(agent_id)
        self.project_root = Path.cwd()
    
    def extract_code_memories(self) -> CodeContext:
        """Extract code-relevant memories from the system"""
        # Search for code-related memories
        code_memories = []
        
        queries = [
            "tech stack",
            "programming language",
            "framework",
            "convention",
            "pattern",
            "architecture",
            "avoid",
            "never do"
        ]
        
        for query in queries:
            results = self.memory.recall(query, k=5)
            code_memories.extend(results)
        
        # Deduplicate
        seen = set()
        unique_memories = []
        for mem in code_memories:
            if mem not in seen:
                seen.add(mem)
                unique_memories.append(mem)
        
        # Extract tech stack
        tech_stack = self._extract_tech_stack(unique_memories)
        
        # Extract conventions
        conventions = self._extract_conventions(unique_memories)
        
        # Extract patterns
        patterns = self._extract_patterns(unique_memories)
        
        # Extract anti-patterns
        avoid = self._extract_avoid(unique_memories)
        
        return CodeContext(
            project_name=self._detect_project_name(),
            description=self._detect_project_description(),
            tech_stack=tech_stack,
            conventions=conventions,
            patterns=patterns,
            avoid=avoid,
            examples=self._extract_examples(),
            memories=unique_memories
        )
    
    def _detect_project_name(self) -> str:
        """Detect project name from git or directory"""
        # Try git
        git_dir = self.project_root / ".git"
        if git_dir.exists():
            config = self.project_root / ".git" / "config"
            if config.exists():
                content = config.read_text()
                for line in content.split('\n'):
                    if 'url' in line and 'github' in line:
                        # Extract repo name from URL
                        parts = line.split('/')
                        if parts:
                            return parts[-1].replace('.git', '').strip()
        
        # Fallback to directory name
        return self.project_root.name
    
    def _detect_project_description(self) -> str:
        """Detect project description from README or memory"""
        readme = self.project_root / "README.md"
        if readme.exists():
            lines = readme.read_text().split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    return line[:200]
        
        return "Project context managed by OpenClaw Memory System"
    
    def _extract_tech_stack(self, memories: List[str]) -> List[str]:
        """Extract technology stack from memories"""
        tech_keywords = [
            "python", "javascript", "typescript", "rust", "go", "java",
            "react", "vue", "angular", "svelte",
            "docker", "kubernetes", "aws", "gcp", "azure",
            "postgresql", "mysql", "mongodb", "redis",
            "fastapi", "flask", "django", "express",
            "tensorflow", "pytorch", "scikit-learn"
        ]
        
        found = []
        for mem in memories:
            mem_lower = mem.lower()
            for tech in tech_keywords:
                if tech in mem_lower and tech not in found:
                    found.append(tech)
        
        return found[:10]  # Limit
    
    def _extract_conventions(self, memories: List[str]) -> List[str]:
        """Extract coding conventions"""
        conventions = []
        
        for mem in memories:
            mem_lower = mem.lower()
            if any(word in mem_lower for word in ["prefer", "use", "should", "always", "convention"]):
                if len(mem) < 200:  # Keep it concise
                    conventions.append(mem)
        
        return conventions[:10]
    
    def _extract_patterns(self, memories: List[str]) -> List[str]:
        """Extract design patterns"""
        patterns = []
        
        for mem in memories:
            mem_lower = mem.lower()
            if any(word in mem_lower for word in ["pattern", "structure", "organize", "module", "component"]):
                if len(mem) < 200:
                    patterns.append(mem)
        
        return patterns[:10]
    
    def _extract_avoid(self, memories: List[str]) -> List[str]:
        """Extract anti-patterns / things to avoid"""
        avoid = []
        
        for mem in memories:
            mem_lower = mem.lower()
            if any(word in mem_lower for word in ["avoid", "never", "don't", "bad", "wrong"]):
                if len(mem) < 200:
                    avoid.append(mem)
        
        return avoid[:10]
    
    def _extract_examples(self) -> List[Dict[str, str]]:
        """Extract code examples from project"""
        examples = []
        
        # Look for example files
        example_dirs = ["examples", "samples", "demo"]
        for dir_name in example_dirs:
            example_dir = self.project_root / dir_name
            if example_dir.exists():
                for file in example_dir.glob("*.py")[:3]:  # First 3 Python files
                    try:
                        code = file.read_text()[:500]  # First 500 chars
                        examples.append({
                            "name": file.name,
                            "code": code
                        })
                    except:
                        pass
        
        return examples
    
    def export_for_claude_code(self, output_path: Optional[Path] = None) -> Path:
        """Export context for Claude Code"""
        context = self.extract_code_memories()
        
        if output_path is None:
            output_path = self.project_root / "CLAUDE.md"
        
        content = context.to_claude_code()
        output_path.write_text(content)
        
        print(f"Exported Claude Code context to: {output_path}")
        return output_path
    
    def export_for_opencode(self, output_path: Optional[Path] = None) -> Path:
        """Export context for OpenCode"""
        context = self.extract_code_memories()
        
        if output_path is None:
            output_path = WORKSPACE_DIR / ".opencode_memory.json"
        
        data = context.to_opencode()
        output_path.write_text(json.dumps(data, indent=2))
        
        print(f"Exported OpenCode context to: {output_path}")
        return output_path
    
    def export_for_cursor(self, output_path: Optional[Path] = None) -> Path:
        """Export context for Cursor"""
        context = self.extract_code_memories()
        
        if output_path is None:
            output_path = self.project_root / ".cursorrules"
        
        content = context.to_cursor()
        output_path.write_text(content)
        
        print(f"Exported Cursor context to: {output_path}")
        return output_path
    
    def export_for_copilot(self, output_path: Optional[Path] = None) -> Path:
        """Export context for GitHub Copilot"""
        context = self.extract_code_memories()
        
        if output_path is None:
            output_path = self.project_root / ".github" / "copilot-instructions.md"
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = context.to_copilot()
        output_path.write_text(content)
        
        print(f"Exported Copilot context to: {output_path}")
        return output_path
    
    def export_all(self) -> Dict[str, Path]:
        """Export for all platforms"""
        return {
            "claude_code": self.export_for_claude_code(),
            "opencode": self.export_for_opencode(),
            "cursor": self.export_for_cursor(),
            "copilot": self.export_for_copilot()
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Export memory context for AI code platforms"
    )
    parser.add_argument("--agent", default="default", help="Agent ID")
    parser.add_argument("--platform", 
                        choices=["claude", "opencode", "cursor", "copilot", "all"],
                        default="all",
                        help="Target platform")
    parser.add_argument("--output", help="Output file path")
    
    args = parser.parse_args()
    
    integration = AIPlatformIntegration(args.agent)
    
    if args.platform == "claude":
        integration.export_for_claude_code(Path(args.output) if args.output else None)
    elif args.platform == "opencode":
        integration.export_for_opencode(Path(args.output) if args.output else None)
    elif args.platform == "cursor":
        integration.export_for_cursor(Path(args.output) if args.output else None)
    elif args.platform == "copilot":
        integration.export_for_copilot(Path(args.output) if args.output else None)
    else:
        paths = integration.export_all()
        print("\nExported for all platforms:")
        for platform, path in paths.items():
            print(f"  {platform}: {path}")


if __name__ == "__main__":
    main()