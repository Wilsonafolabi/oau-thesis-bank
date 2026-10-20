import uuid
from typing import List, Dict
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import AIDocument
from researcher_intelligence.models import ThesisRelationship, RelationshipType, RelationshipConfidence

class LineageGraphBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_topic_relationships(self) -> List[Dict]:
        result = await self.db.execute(select(AIDocument).where(AIDocument.thesis_metadata.is_not(None)))
        theses = result.scalars().all()
        
        topic_to_theses = defaultdict(list)
        for thesis in theses:
            if not thesis.thesis_metadata: continue
            for topic in thesis.thesis_metadata.get("topics", []):
                topic_to_theses[topic].append(thesis.id)
        
        relationships = []
        for topic, thesis_ids in topic_to_theses.items():
            if len(thesis_ids) < 2: continue
            for i in range(len(thesis_ids)):
                for j in range(i + 1, len(thesis_ids)):
                    relationships.append({
                        "source_thesis_id": thesis_ids[i], "target_thesis_id": thesis_ids[j],
                        "relationship_type": RelationshipType.SAME_TOPIC, "confidence": RelationshipConfidence.CONFIRMED,
                        "evidence": {"shared_topic": topic, "source": "explicit_topic_metadata"}
                    })
        return relationships
    
    async def build_lineage_graph(self) -> Dict:
        all_relationships = await self.find_topic_relationships()
        seen, relationships_created = set(), 0
        
        for rel_data in all_relationships:
            key = (rel_data["source_thesis_id"], rel_data["target_thesis_id"], rel_data["relationship_type"])
            if key in seen: continue
            seen.add(key)
            
            result = await self.db.execute(select(ThesisRelationship).where(
                ThesisRelationship.source_thesis_id == rel_data["source_thesis_id"],
                ThesisRelationship.target_thesis_id == rel_data["target_thesis_id"],
                ThesisRelationship.relationship_type == rel_data["relationship_type"]
            ))
            if not result.scalar_one_or_none():
                self.db.add(ThesisRelationship(id=str(uuid.uuid4()), **rel_data))
                relationships_created += 1
        
        await self.db.commit()
        return {"total_relationships_found": len(all_relationships), "unique_relationships_created": relationships_created}
    
    async def get_thesis_lineage(self, thesis_id: str, max_depth: int = 2, limit: int = 50) -> Dict:
        result = await self.db.execute(select(ThesisRelationship).where(
            (ThesisRelationship.source_thesis_id == thesis_id) | (ThesisRelationship.target_thesis_id == thesis_id)
        ).limit(limit))
        relationships = result.scalars().all()
        
        nodes, edges = {}, []
        thesis_result = await self.db.execute(select(AIDocument).where(AIDocument.id == thesis_id))
        thesis = thesis_result.scalar_one_or_none()
        if not thesis: return {"nodes": [], "edges": []}
        
        nodes[thesis_id] = {"id": thesis_id, "title": thesis.thesis_metadata.get("title", "Unknown") if thesis.thesis_metadata else "Unknown", "type": "thesis"}
        
        for rel in relationships:
            other_id = rel.target_thesis_id if rel.source_thesis_id == thesis_id else rel.source_thesis_id
            other_result = await self.db.execute(select(AIDocument).where(AIDocument.id == other_id))
            other_thesis = other_result.scalar_one_or_none()
            
            if other_thesis and other_thesis.access_level != "private":
                nodes[other_id] = {"id": other_id, "title": other_thesis.thesis_metadata.get("title", "Unknown") if other_thesis.thesis_metadata else "Unknown", "type": "thesis"}
                edges.append({"source": rel.source_thesis_id, "target": rel.target_thesis_id, "type": rel.relationship_type.value, "confidence": rel.confidence.value, "evidence": rel.evidence})
        
        return {"nodes": list(nodes.values()), "edges": edges}


