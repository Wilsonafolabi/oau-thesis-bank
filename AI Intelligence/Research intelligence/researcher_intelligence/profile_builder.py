import hashlib, uuid
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import AIDocument
from researcher_intelligence.models import ResearcherProfile, ResearcherThesisRelationship, RelationshipType, RelationshipConfidence

class ResearcherProfileBuilder:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _generate_researcher_id(self, name: str, department: Optional[str] = None) -> str:
        key = f"{name.lower().strip()}|{department or ''}".strip("|")
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    async def extract_researchers_from_thesis(self, thesis_id: str) -> List[Dict]:
        result = await self.db.execute(select(AIDocument).where(AIDocument.id == thesis_id))
        thesis = result.scalar_one_or_none()
        if not thesis or not thesis.thesis_metadata: return []
        
        metadata = thesis.thesis_metadata
        researchers = []
        if metadata.get("author"):
            researchers.append({"name": metadata["author"], "department": metadata.get("department"), "institution": metadata.get("institution", "OAU"), "role": "author", "thesis_id": thesis_id})
        if metadata.get("supervisor"):
            researchers.append({"name": metadata["supervisor"], "department": metadata.get("department"), "institution": metadata.get("institution", "OAU"), "role": "supervisor", "thesis_id": thesis_id})
        return researchers
    
    async def build_profile(self, researcher_data: Dict) -> ResearcherProfile:
        researcher_id = self._generate_researcher_id(researcher_data["name"], researcher_data.get("department"))
        result = await self.db.execute(select(ResearcherProfile).where(ResearcherProfile.id == researcher_id))
        profile = result.scalar_one_or_none()
        
        if not profile:
            profile = ResearcherProfile(id=researcher_id, name=researcher_data["name"], department=researcher_data.get("department"), institution=researcher_data.get("institution", "OAU"), visibility="public")
            self.db.add(profile)
        elif researcher_data.get("department") and not profile.department:
            profile.department = researcher_data["department"]
        await self.db.flush()
        return profile
    
    async def link_researcher_to_thesis(self, researcher_id: str, thesis_id: str, relationship_type: RelationshipType, evidence: Dict) -> ResearcherThesisRelationship:
        result = await self.db.execute(select(ResearcherThesisRelationship).where(
            ResearcherThesisRelationship.researcher_id == researcher_id,
            ResearcherThesisRelationship.thesis_id == thesis_id,
            ResearcherThesisRelationship.relationship_type == relationship_type
        ))
        existing = result.scalar_one_or_none()
        if existing: return existing
        
        relationship = ResearcherThesisRelationship(id=str(uuid.uuid4()), researcher_id=researcher_id, thesis_id=thesis_id, relationship_type=relationship_type, confidence=RelationshipConfidence.CONFIRMED, evidence=evidence)
        self.db.add(relationship)
        await self.db.flush()
        return relationship
    
    async def process_thesis(self, thesis_id: str) -> Dict:
        researchers_data = await self.extract_researchers_from_thesis(thesis_id)
        if not researchers_data: return {"profiles_created": 0, "relationships_created": 0}
        
        profiles_created, relationships_created = 0, 0
        for researcher_data in researchers_data:
            profile = await self.build_profile(researcher_data)
            rel_type = RelationshipType.AUTHOR_OF if researcher_data["role"] == "author" else RelationshipType.SUPERVISED
            await self.link_researcher_to_thesis(profile.id, thesis_id, rel_type, {"source": "thesis_metadata", "field": researcher_data["role"], "value": researcher_data["name"]})
            relationships_created += 1
        
        await self.db.commit()
        return {"profiles_created": profiles_created, "relationships_created": relationships_created, "researchers": [r["name"] for r in researchers_data]}

