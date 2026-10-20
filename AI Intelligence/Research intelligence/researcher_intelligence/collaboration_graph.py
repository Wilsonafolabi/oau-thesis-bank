import uuid
from typing import List, Dict, Tuple
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from researcher_intelligence.models import ResearcherProfile, ResearcherThesisRelationship, ResearcherCollaboration, RelationshipType, RelationshipConfidence

class CollaborationGraphBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_collaborations(self) -> List[Tuple[str, str, List[str]]]:
        result = await self.db.execute(select(ResearcherThesisRelationship))
        relationships = result.scalars().all()
        
        thesis_to_researchers = defaultdict(list)
        for rel in relationships:
            thesis_to_researchers[rel.thesis_id].append(rel.researcher_id)
        
        collaborations = []
        for thesis_id, researcher_ids in thesis_to_researchers.items():
            if len(researcher_ids) < 2: continue
            for i in range(len(researcher_ids)):
                for j in range(i + 1, len(researcher_ids)):
                    a_id, b_id = sorted([researcher_ids[i], researcher_ids[j]])
                    collaborations.append((a_id, b_id, [thesis_id]))
        return collaborations
    
    async def build_collaboration_graph(self) -> Dict:
        collaborations = await self.find_collaborations()
        pair_to_theses = defaultdict(list)
        for a_id, b_id, thesis_ids in collaborations:
            pair_to_theses[(a_id, b_id)].extend(thesis_ids)
        
        collaborations_created = 0
        for (a_id, b_id), thesis_ids in pair_to_theses.items():
            unique_theses = list(set(thesis_ids))
            result = await self.db.execute(select(ResearcherCollaboration).where(
                ResearcherCollaboration.researcher_a_id == a_id, ResearcherCollaboration.researcher_b_id == b_id
            ))
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.evidence = {"thesis_ids": unique_theses}
                existing.collaboration_count = len(unique_theses)
            else:
                collab = ResearcherCollaboration(id=str(uuid.uuid4()), researcher_a_id=a_id, researcher_b_id=b_id, relationship_type=RelationshipType.COLLABORATED_WITH, confidence=RelationshipConfidence.CONFIRMED, evidence={"thesis_ids": unique_theses}, collaboration_count=len(unique_theses))
                self.db.add(collab)
                collaborations_created += 1
        
        await self.db.commit()
        return {"total_collaborations": len(pair_to_theses), "new_collaborations_created": collaborations_created}
    
    async def get_collaborators(self, researcher_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        result = await self.db.execute(select(ResearcherCollaboration).where(
            (ResearcherCollaboration.researcher_a_id == researcher_id) | (ResearcherCollaboration.researcher_b_id == researcher_id)
        ).limit(limit).offset(offset))
        collaborations = result.scalars().all()
        
        collaborators = []
        for collab in collaborations:
            other_id = collab.researcher_b_id if collab.researcher_a_id == researcher_id else collab.researcher_a_id
            profile_result = await self.db.execute(select(ResearcherProfile).where(ResearcherProfile.id == other_id))
            other_profile = profile_result.scalar_one_or_none()
            
            if other_profile and other_profile.visibility != "private":
                collaborators.append({
                    "researcher_id": other_id, "name": other_profile.name, "department": other_profile.department,
                    "collaboration_count": collab.collaboration_count, "evidence": collab.evidence, "confidence": collab.confidence.value
                })
        return collaborators
