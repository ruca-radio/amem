#!/usr/bin/env python3
"""
Auto-Extraction Service for OpenClaw Memory System
Automatically extracts facts, preferences, and decisions from conversations.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# Import memory system
import sys
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, MemoryType, MemoryTier


@dataclass
class ExtractedFact:
    """A fact extracted from conversation"""
    content: str
    fact_type: str  # fact, preference, decision, skill
    confidence: float
    source_text: str
    timestamp: datetime


class SimpleExtractor:
    """
    Rule-based extractor (no LLM required).
    Uses patterns and heuristics to extract structured information.
    """
    
    # Patterns for extraction
    PATTERNS = {
        "preference": [
            r"(?:i|user|they) prefer(?:s)? (.+)",
            r"(?:i|user|they) like(?:s)? (.+)",
            r"(?:i|user|they) want(?:s)? (.+)",
            r"(?:i|user|they) need(?:s)? (.+)",
            r"(?:don't|doesn't) like (.+)",
            r"(?:never|always) (.+)",
        ],
        "fact": [
            r"(?:i|user|they) (?:run|use|have|work with|manage) (.+)",
            r"(?:my|user's|their) (.+) is (.+)",
            r"(?:i|user|they) (?:am|is|are) (.+)",
        ],
        "decision": [
            r"(?:decided|chose|picked|went with) (.+)",
            r"(?:we|i|user) will (.+)",
            r"(?:let's|let us) (.+)",
        ],
        "skill": [
            r"(?:know|knew|understand|learned) (?:how to )?(.+)",
            r"(?:can|could) (.+)",
            r"(?:fixed|solved|debugged|built|created) (.+)",
        ]
    }
    
    def __init__(self):
        self.compiled_patterns = {
            fact_type: [re.compile(p, re.IGNORECASE) for p in patterns]
            for fact_type, patterns in self.PATTERNS.items()
        }
    
    def extract(self, text: str, speaker: str = "user") -> List[ExtractedFact]:
        """
        Extract facts from text using patterns.
        
        Args:
            text: Conversation text to analyze
            speaker: "user" or "assistant"
        
        Returns:
            List of extracted facts
        """
        facts = []
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short fragments
                continue
            
            for fact_type, patterns in self.compiled_patterns.items():
                for pattern in patterns:
                    match = pattern.search(sentence)
                    if match:
                        # Extract the content
                        groups = match.groups()
                        content = groups[0] if groups else sentence
                        
                        # Clean up
                        content = content.strip()
                        if len(content) < 5:
                            continue
                        
                        # Format as statement
                        if speaker == "user":
                            content = f"User {fact_type}: {content}"
                        else:
                            content = f"Agent {fact_type}: {content}"
                        
                        # Calculate confidence based on match quality
                        confidence = self._calculate_confidence(sentence, pattern, match)
                        
                        fact = ExtractedFact(
                            content=content,
                            fact_type=fact_type,
                            confidence=confidence,
                            source_text=sentence,
                            timestamp=datetime.now()
                        )
                        facts.append(fact)
                        break  # Only first match per type
        
        # Deduplicate similar facts
        facts = self._deduplicate(facts)
        
        return facts
    
    def _calculate_confidence(self, sentence: str, pattern, match) -> float:
        """Calculate confidence score for extraction"""
        confidence = 0.5  # Base confidence
        
        # Longer matches are more specific
        match_len = len(match.group(0))
        if match_len > 20:
            confidence += 0.1
        if match_len > 40:
            confidence += 0.1
        
        # Complete sentences are more reliable
        if sentence[0].isupper() and len(sentence) > 20:
            confidence += 0.1
        
        # Contains specific keywords
        specific_words = ['specifically', 'exactly', 'always', 'never', 'only']
        if any(w in sentence.lower() for w in specific_words):
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _deduplicate(self, facts: List[ExtractedFact]) -> List[ExtractedFact]:
        """Remove duplicate or very similar facts"""
        unique = []
        seen_contents = set()
        
        for fact in facts:
            # Normalize for comparison
            normalized = fact.content.lower().strip()
            normalized = re.sub(r'\s+', ' ', normalized)
            
            # Check for similarity with existing
            is_duplicate = False
            for seen in seen_contents:
                # Simple Jaccard similarity
                set1 = set(normalized.split())
                set2 = set(seen.split())
                if set1 and set2:
                    jaccard = len(set1 & set2) / len(set1 | set2)
                    if jaccard > 0.8:  # 80% similar
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique.append(fact)
                seen_contents.add(normalized)
        
        return unique


class AutoMemoryExtractor:
    """
    Automatic memory extraction from conversations.
    Integrates with MemoryTools to store extracted facts.
    """
    
    def __init__(self, agent_id: str = "default", min_confidence: float = 0.6):
        self.agent_id = agent_id
        self.memory = MemoryTools(agent_id)
        self.extractor = SimpleExtractor()
        self.min_confidence = min_confidence
        self.extraction_log: List[Dict] = []
    
    def process_turn(self, user_message: str, assistant_response: str) -> List[ExtractedFact]:
        """
        Process a conversation turn and extract memories.
        
        Args:
            user_message: User's input
            assistant_response: Assistant's response
        
        Returns:
            List of extracted and stored facts
        """
        all_facts = []
        
        # Extract from user message
        user_facts = self.extractor.extract(user_message, speaker="user")
        all_facts.extend(user_facts)
        
        # Extract from assistant response (less priority)
        assistant_facts = self.extractor.extract(assistant_response, speaker="assistant")
        # Filter to only high-confidence assistant facts
        assistant_facts = [f for f in assistant_facts if f.confidence > 0.7]
        all_facts.extend(assistant_facts)
        
        # Store high-confidence facts
        stored_facts = []
        for fact in all_facts:
            if fact.confidence >= self.min_confidence:
                self._store_fact(fact)
                stored_facts.append(fact)
        
        # Log extraction
        self.extraction_log.append({
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message[:100],
            "facts_extracted": len(stored_facts),
            "facts": [{"type": f.fact_type, "content": f.content[:50]} for f in stored_facts]
        })
        
        return stored_facts
    
    def _store_fact(self, fact: ExtractedFact):
        """Store extracted fact to appropriate memory tier"""
        # Determine importance based on confidence and type
        importance = fact.confidence
        
        # Preferences and decisions are more important
        if fact.fact_type in ["preference", "decision"]:
            importance = min(importance + 0.2, 1.0)
            permanent = True
        elif fact.fact_type == "skill":
            importance = min(importance + 0.1, 1.0)
            permanent = True
        else:
            permanent = importance > 0.75
        
        # Store via MemoryTools
        self.memory.remember(
            content=fact.content,
            memory_type=fact.fact_type,
            importance=importance,
            permanent=permanent
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get extraction statistics"""
        return {
            "total_extractions": len(self.extraction_log),
            "total_facts_stored": sum(log["facts_extracted"] for log in self.extraction_log),
            "recent_extractions": self.extraction_log[-10:]
        }


# Demo
if __name__ == "__main__":
    print("Auto-Extraction Service Demo")
    print("=" * 60)
    
    extractor = AutoMemoryExtractor("demo", min_confidence=0.5)
    
    # Simulate conversation turns
    conversations = [
        (
            "I prefer Python for automation scripts and dislike JavaScript for backend work.",
            "I'll keep that in mind. Python is great for automation with its rich ecosystem."
        ),
        (
            "I run Proxmox at home with a few VMs for testing.",
            "Proxmox is excellent for home labs. I can help you manage those VMs."
        ),
        (
            "I decided to use Docker Compose for this project instead of Kubernetes.",
            "Good choice for a smaller project. Docker Compose is much simpler to set up."
        ),
        (
            "I learned how to debug networking issues in containers yesterday.",
            "That's a valuable skill. Container networking can be tricky."
        ),
    ]
    
    for i, (user_msg, assistant_msg) in enumerate(conversations, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {user_msg[:60]}...")
        
        facts = extractor.process_turn(user_msg, assistant_msg)
        
        print(f"Extracted {len(facts)} facts:")
        for fact in facts:
            print(f"  [{fact.fact_type}] {fact.content[:50]}... (conf: {fact.confidence:.2f})")
    
    print("\n" + "=" * 60)
    print("Extraction Stats:")
    stats = extractor.get_stats()
    print(f"  Total facts stored: {stats['total_facts_stored']}")
    print("\nMemory contents:")
    results = extractor.memory.recall("preference", k=5)
    for r in results:
        print(f"  - {r[:60]}...")