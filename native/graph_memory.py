#!/usr/bin/env python3
"""
Graph Memory Layer for OpenClaw Memory System
Adds entity-relationship graph on top of semantic memory.
Enables complex queries like "What projects does user X work on?"
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib

# Import memory system
import sys
NATIVE_DIR = Path(__file__).parent
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))

from openclaw_memory import MemoryTools, WORKSPACE_DIR


class RelationType(Enum):
    """Types of relationships between entities"""
    WORKS_ON = "works_on"
    KNOWS = "knows"
    USES = "uses"
    PREFERS = "prefers"
    HAS = "has"
    PART_OF = "part_of"
    LOCATED_AT = "located_at"
    RELATED_TO = "related_to"


@dataclass
class Entity:
    """A node in the knowledge graph"""
    id: str
    name: str
    entity_type: str  # person, project, technology, location, organization
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.entity_type,
            "properties": self.properties,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Relation:
    """An edge in the knowledge graph"""
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source_id,
            "target": self.target_id,
            "type": self.relation_type.value,
            "properties": self.properties,
            "created_at": self.created_at.isoformat()
        }


class SimpleEntityExtractor:
    """Extract entities from text using patterns"""
    
    # Entity patterns
    PATTERNS = {
        "technology": [
            r"\b(Python|JavaScript|TypeScript|Rust|Go|Java|C\+\+|C#|Ruby|PHP|Swift|Kotlin)\b",
            r"\b(Docker|Kubernetes|AWS|GCP|Azure|Proxmox|VMware|OpenClaw)\b",
            r"\b(PostgreSQL|MySQL|MongoDB|Redis|SQLite|Elasticsearch)\b",
            r"\b(Linux|macOS|Windows|Ubuntu|Debian|CentOS|Alpine)\b",
        ],
        "project": [
            r"(?:project|app|application|system|service) (?:called|named)? ['\"]?([A-Z][a-zA-Z0-9_-]+)['\"]?",
            r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*Project)\b",  # CamelCase Project
        ],
        "location": [
            r"\b(home|office|datacenter|cloud|aws|gcp|azure)\b",
        ],
    }
    
    def __init__(self):
        self.compiled = {
            etype: [re.compile(p, re.IGNORECASE) for p in patterns]
            for etype, patterns in self.PATTERNS.items()
        }
    
    def extract(self, text: str) -> List[Entity]:
        """Extract entities from text"""
        entities = []
        seen = set()
        
        for entity_type, patterns in self.compiled.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    name = match.group(1) if match.groups() else match.group(0)
                    name = name.strip()
                    
                    # Normalize
                    name_lower = name.lower()
                    if name_lower in seen:
                        continue
                    seen.add(name_lower)
                    
                    # Create entity
                    entity_id = hashlib.sha256(f"{entity_type}:{name_lower}".encode()).hexdigest()[:16]
                    entity = Entity(
                        id=entity_id,
                        name=name,
                        entity_type=entity_type
                    )
                    entities.append(entity)
        
        return entities


class GraphMemory:
    """
    Graph-based memory layer.
    Stores entities and relationships for complex querying.
    """
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.graph_dir = WORKSPACE_DIR / "memory_graph"
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.entity_extractor = SimpleEntityExtractor()
        
        self._load()
    
    def _load(self):
        """Load graph from disk"""
        entities_file = self.graph_dir / "entities.json"
        relations_file = self.graph_dir / "relations.json"
        
        if entities_file.exists():
            try:
                with open(entities_file) as f:
                    data = json.load(f)
                    for e_data in data:
                        entity = Entity(
                            id=e_data["id"],
                            name=e_data["name"],
                            entity_type=e_data["type"],
                            properties=e_data.get("properties", {}),
                            created_at=datetime.fromisoformat(e_data["created_at"])
                        )
                        self.entities[entity.id] = entity
            except Exception as e:
                print(f"[Graph] Failed to load entities: {e}")
        
        if relations_file.exists():
            try:
                with open(relations_file) as f:
                    data = json.load(f)
                    for r_data in data:
                        relation = Relation(
                            id=r_data["id"],
                            source_id=r_data["source"],
                            target_id=r_data["target"],
                            relation_type=RelationType(r_data["type"]),
                            properties=r_data.get("properties", {}),
                            created_at=datetime.fromisoformat(r_data["created_at"])
                        )
                        self.relations[relation.id] = relation
            except Exception as e:
                print(f"[Graph] Failed to load relations: {e}")
    
    def _save(self):
        """Save graph to disk"""
        entities_file = self.graph_dir / "entities.json"
        relations_file = self.graph_dir / "relations.json"
        
        with open(entities_file, 'w') as f:
            json.dump([e.to_dict() for e in self.entities.values()], f, indent=2)
        
        with open(relations_file, 'w') as f:
            json.dump([r.to_dict() for r in self.relations.values()], f, indent=2)
    
    def add_entity(self, name: str, entity_type: str, properties: Dict = None) -> Entity:
        """Add an entity to the graph"""
        entity_id = hashlib.sha256(f"{entity_type}:{name.lower()}".encode()).hexdigest()[:16]
        
        if entity_id in self.entities:
            # Update existing
            self.entities[entity_id].properties.update(properties or {})
        else:
            # Create new
            entity = Entity(
                id=entity_id,
                name=name,
                entity_type=entity_type,
                properties=properties or {}
            )
            self.entities[entity_id] = entity
        
        self._save()
        return self.entities[entity_id]
    
    def add_relation(self, source_name: str, target_name: str, 
                     relation_type: RelationType, properties: Dict = None) -> Optional[Relation]:
        """Add a relationship between entities"""
        # Find entities
        source = self._find_entity(source_name)
        target = self._find_entity(target_name)
        
        if not source or not target:
            return None
        
        relation_id = hashlib.sha256(
            f"{source.id}:{relation_type.value}:{target.id}".encode()
        ).hexdigest()[:16]
        
        relation = Relation(
            id=relation_id,
            source_id=source.id,
            target_id=target.id,
            relation_type=relation_type,
            properties=properties or {}
        )
        
        self.relations[relation_id] = relation
        self._save()
        return relation
    
    def _find_entity(self, name: str) -> Optional[Entity]:
        """Find entity by name (case-insensitive)"""
        name_lower = name.lower()
        for entity in self.entities.values():
            if entity.name.lower() == name_lower:
                return entity
        return None
    
    def extract_from_text(self, text: str) -> Tuple[List[Entity], List[Relation]]:
        """Extract entities and relations from text"""
        # Extract entities
        entities = self.entity_extractor.extract(text)
        
        # Add to graph
        for entity in entities:
            if entity.id not in self.entities:
                self.entities[entity.id] = entity
        
        # Create relations (heuristic: entities in same sentence are related)
        relations = []
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            sent_entities = self.entity_extractor.extract(sentence)
            if len(sent_entities) >= 2:
                # Create relations between entities in same sentence
                for i, source in enumerate(sent_entities):
                    for target in sent_entities[i+1:]:
                        relation = self.add_relation(
                            source.name, target.name, 
                            RelationType.RELATED_TO,
                            {"context": sentence[:100]}
                        )
                        if relation:
                            relations.append(relation)
        
        self._save()
        return entities, relations
    
    def query(self, entity_name: str, relation_type: Optional[RelationType] = None) -> List[Dict]:
        """
        Query the graph for relationships.
        
        Example: query("Python", RelationType.USES) -> what uses Python?
        """
        entity = self._find_entity(entity_name)
        if not entity:
            return []
        
        results = []
        
        # Find relations where entity is source or target
        for relation in self.relations.values():
            if relation_type and relation.relation_type != relation_type:
                continue
            
            if relation.source_id == entity.id:
                target = self.entities.get(relation.target_id)
                if target:
                    results.append({
                        "direction": "outgoing",
                        "relation": relation.relation_type.value,
                        "entity": target.to_dict()
                    })
            
            elif relation.target_id == entity.id:
                source = self.entities.get(relation.source_id)
                if source:
                    results.append({
                        "direction": "incoming",
                        "relation": relation.relation_type.value,
                        "entity": source.to_dict()
                    })
        
        return results
    
    def get_entity_network(self, entity_name: str, depth: int = 1) -> Dict:
        """Get the network around an entity (neighbors and their neighbors)"""
        entity = self._find_entity(entity_name)
        if not entity:
            return {}
        
        network = {
            "center": entity.to_dict(),
            "nodes": [],
            "edges": []
        }
        
        visited = {entity.id}
        current_level = {entity.id}
        
        for d in range(depth):
            next_level = set()
            for entity_id in current_level:
                for relation in self.relations.values():
                    if relation.source_id == entity_id:
                        if relation.target_id not in visited:
                            target = self.entities.get(relation.target_id)
                            if target:
                                network["nodes"].append(target.to_dict())
                                network["edges"].append(relation.to_dict())
                                next_level.add(target.id)
                                visited.add(target.id)
                    
                    elif relation.target_id == entity_id:
                        if relation.source_id not in visited:
                            source = self.entities.get(relation.source_id)
                            if source:
                                network["nodes"].append(source.to_dict())
                                network["edges"].append(relation.to_dict())
                                next_level.add(source.id)
                                visited.add(source.id)
            
            current_level = next_level
        
        return network
    
    def stats(self) -> Dict:
        """Get graph statistics"""
        return {
            "entities": len(self.entities),
            "relations": len(self.relations),
            "entity_types": {}
        }


class MemoryGraphTools:
    """High-level interface combining semantic and graph memory"""
    
    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.memory = MemoryTools(agent_id)
        self.graph = GraphMemory(agent_id)
    
    def remember(self, content: str, extract_entities: bool = True, **kwargs):
        """Store memory and optionally extract entities"""
        # Store in semantic memory
        result = self.memory.remember(content, **kwargs)
        
        # Extract entities for graph
        if extract_entities:
            entities, relations = self.graph.extract_from_text(content)
            if entities:
                print(f"[Graph] Extracted {len(entities)} entities, {len(relations)} relations")
        
        return result
    
    def recall(self, query: str, use_graph: bool = False, **kwargs):
        """Recall memories, optionally using graph"""
        if use_graph:
            # Try graph query first
            graph_results = self.graph.query(query)
            if graph_results:
                return {
                    "type": "graph",
                    "results": graph_results
                }
        
        # Fall back to semantic search
        return self.memory.recall(query, **kwargs)
    
    def ask(self, question: str) -> str:
        """
        Answer questions using graph + semantic memory.
        
        Examples:
        - "What technologies does user know?"
        - "What projects is user working on?"
        """
        # Parse question for entity
        words = question.lower().split()
        
        # Look for entities in question
        for word in words:
            entity = self.graph._find_entity(word)
            if entity:
                network = self.graph.get_entity_network(entity.name, depth=1)
                if network.get("nodes"):
                    response = f"{entity.name} ({entity.entity_type}) is related to:\n"
                    for node in network["nodes"][:5]:
                        response += f"  - {node['name']} ({node['type']})\n"
                    return response
        
        # Fall back to semantic search
        results = self.memory.recall(question, k=3)
        if results:
            return "Based on memory:\n" + "\n".join(f"  - {r[:80]}" for r in results)
        
        return "No relevant information found in memory."


# Demo
if __name__ == "__main__":
    print("Graph Memory Layer Demo")
    print("=" * 60)
    
    tools = MemoryGraphTools("demo")
    
    # Add some memories with entity extraction
    memories = [
        "I use Python and Docker for my home automation project",
        "I run Proxmox with Ubuntu VMs in my home lab",
        "I prefer PostgreSQL over MySQL for new projects",
        "I'm learning Rust for systems programming",
    ]
    
    print("\nAdding memories with entity extraction...")
    for mem in memories:
        print(f"\n  Memory: {mem}")
        tools.remember(mem, permanent=True)
    
    print("\n" + "=" * 60)
    print("Graph Statistics:")
    stats = tools.graph.stats()
    print(f"  Entities: {stats['entities']}")
    print(f"  Relations: {stats['relations']}")
    
    print("\nEntities in graph:")
    for entity in list(tools.graph.entities.values())[:10]:
        print(f"  - {entity.name} ({entity.entity_type})")
    
    print("\nQuery: What is related to Python?")
    results = tools.graph.query("Python")
    for r in results:
        print(f"  {r['direction']}: {r['relation']} -> {r['entity']['name']}")
    
    print("\nAsk: What technologies does user know?")
    answer = tools.ask("What technologies does user know")
    print(answer)