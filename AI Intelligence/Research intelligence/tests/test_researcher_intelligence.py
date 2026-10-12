import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from researcher_intelligence.profile_builder import ResearcherProfileBuilder
from researcher_intelligence.collaboration_graph import CollaborationGraphBuilder
from researcher_intelligence.lineage_graph import LineageGraphBuilder
from researcher_intelligence.models import ResearcherProfile, ResearcherThesisRelationship, ResearcherCollaboration, ThesisRelationship, RelationshipType, RelationshipConfidence
from db.models import AIDocument

@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def sample_thesis():
    thesis = MagicMock(spec=AIDocument)
    thesis.id = "thesis-1"
    thesis.thesis_metadata = {"title": "ML for Agriculture", "author": "John Doe", "supervisor": "Jane Smith", "department": "CS", "topics": ["machine learning"]}
    thesis.access_level = "public"
    return thesis

class TestResearcherProfileBuilder:
    @pytest.mark.asyncio
    async def test_extract_researchers_from_thesis(self, mock_db, sample_thesis):
        # Use MagicMock for the Result object, not AsyncMock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_thesis
        mock_db.execute.return_value = mock_result
        
        builder = ResearcherProfileBuilder(mock_db)
        researchers = await builder.extract_researchers_from_thesis("thesis-1")
        
        assert len(researchers) == 2
        assert researchers[0]["name"] == "John Doe"
        assert researchers[1]["role"] == "supervisor"

    @pytest.mark.asyncio
    async def test_extract_researchers_missing_metadata(self, mock_db):
        thesis = MagicMock(spec=AIDocument)
        thesis.id = "thesis-2"
        thesis.thesis_metadata = None
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = thesis
        mock_db.execute.return_value = mock_result
        
        builder = ResearcherProfileBuilder(mock_db)
        assert len(await builder.extract_researchers_from_thesis("thesis-2")) == 0

class TestCollaborationGraphBuilder:
    @pytest.mark.asyncio
    async def test_find_collaborations_from_shared_thesis(self, mock_db):
        rel1 = MagicMock(spec=ResearcherThesisRelationship, thesis_id="thesis-1", researcher_id="researcher-1")
        rel2 = MagicMock(spec=ResearcherThesisRelationship, thesis_id="thesis-1", researcher_id="researcher-2")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rel1, rel2]
        mock_db.execute.return_value = mock_result
        
        builder = CollaborationGraphBuilder(mock_db)
        collaborations = await builder.find_collaborations()
        
        assert len(collaborations) == 1
        assert collaborations[0][0] == "researcher-1"
        assert collaborations[0][1] == "researcher-2"

    @pytest.mark.asyncio
    async def test_get_collaborators_respects_visibility(self, mock_db):
        collab = MagicMock(spec=ResearcherCollaboration, researcher_a_id="researcher-1", researcher_b_id="researcher-2", collaboration_count=2, evidence={"thesis_ids": ["thesis-1"]}, confidence=RelationshipConfidence.CONFIRMED)
        private_profile = MagicMock(spec=ResearcherProfile, id="researcher-2", visibility="private")
        
        mock_collab_result = MagicMock()
        mock_collab_result.scalars.return_value.all.return_value = [collab]
        
        mock_profile_result = MagicMock()
        mock_profile_result.scalar_one_or_none.return_value = private_profile
        
        mock_db.execute.side_effect = [mock_collab_result, mock_profile_result]
        
        builder = CollaborationGraphBuilder(mock_db)
        collaborators = await builder.get_collaborators("researcher-1")
        
        assert len(collaborators) == 0

class TestLineageGraphBuilder:
    @pytest.mark.asyncio
    async def test_find_topic_relationships(self, mock_db):
        t1 = MagicMock(spec=AIDocument, id="thesis-1", thesis_metadata={"topics": ["machine learning"]})
        t2 = MagicMock(spec=AIDocument, id="thesis-2", thesis_metadata={"topics": ["machine learning", "agriculture"]})
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [t1, t2]
        mock_db.execute.return_value = mock_result
        
        builder = LineageGraphBuilder(mock_db)
        relationships = await builder.find_topic_relationships()
        
        assert len(relationships) == 1
        assert relationships[0]["relationship_type"] == RelationshipType.SAME_TOPIC

    @pytest.mark.asyncio
    async def test_lineage_graph_excludes_private_theses(self, mock_db):
        rel = MagicMock(spec=ThesisRelationship, source_thesis_id="thesis-1", target_thesis_id="thesis-2", relationship_type=RelationshipType.SAME_TOPIC, confidence=RelationshipConfidence.CONFIRMED, evidence={})
        
        t1 = MagicMock(spec=AIDocument, id="thesis-1", thesis_metadata={"title": "T1"}, access_level="public")
        t2 = MagicMock(spec=AIDocument, id="thesis-2", thesis_metadata={"title": "T2"}, access_level="private")
        
        mock_rel_result = MagicMock()
        mock_rel_result.scalars.return_value.all.return_value = [rel]
        
        mock_t1_result = MagicMock()
        mock_t1_result.scalar_one_or_none.return_value = t1
        
        mock_t2_result = MagicMock()
        mock_t2_result.scalar_one_or_none.return_value = t2
        
        mock_db.execute.side_effect = [mock_rel_result, mock_t1_result, mock_t2_result]
        
        builder = LineageGraphBuilder(mock_db)
        graph = await builder.get_thesis_lineage("thesis-1")
        
        assert len(graph["nodes"]) == 1
        assert len(graph["edges"]) == 0
