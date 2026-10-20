from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from db.models import Base

class RelationshipType(str, enum.Enum):
    AUTHOR_OF = "author_of"
    SUPERVISED = "supervised"
    COLLABORATED_WITH = "collaborated_with"
    CITES = "cites"
    EXTENDS = "extends"
    SAME_TOPIC = "same_topic"
    SAME_METHOD = "same_method"

class RelationshipConfidence(str, enum.Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    WEAK = "weak"

class ResearcherProfile(Base):
    __tablename__ = "researcher_profiles"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    department = Column(String)
    institution = Column(String, default="Obafemi Awolowo University")
    visibility = Column(String, default="public")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    thesis_authorships = relationship("ResearcherThesisRelationship", foreign_keys="ResearcherThesisRelationship.researcher_id", back_populates="researcher")
    collaborations = relationship("ResearcherCollaboration", foreign_keys="ResearcherCollaboration.researcher_a_id", back_populates="researcher_a")

class ResearcherThesisRelationship(Base):
    __tablename__ = "researcher_thesis_relationships"
    id = Column(String, primary_key=True)
    researcher_id = Column(String, ForeignKey("researcher_profiles.id"), nullable=False)
    thesis_id = Column(String, ForeignKey("ai_documents.id"), nullable=False)
    relationship_type = Column(SAEnum(RelationshipType), nullable=False)
    confidence = Column(SAEnum(RelationshipConfidence), default=RelationshipConfidence.CONFIRMED)
    evidence = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    researcher = relationship("ResearcherProfile", back_populates="thesis_authorships")
    thesis = relationship("AIDocument")

class ResearcherCollaboration(Base):
    __tablename__ = "researcher_collaborations"
    id = Column(String, primary_key=True)
    researcher_a_id = Column(String, ForeignKey("researcher_profiles.id"), nullable=False)
    researcher_b_id = Column(String, ForeignKey("researcher_profiles.id"), nullable=False)
    relationship_type = Column(SAEnum(RelationshipType), default=RelationshipType.COLLABORATED_WITH)
    confidence = Column(SAEnum(RelationshipConfidence), default=RelationshipConfidence.CONFIRMED)
    evidence = Column(JSON)
    collaboration_count = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    researcher_a = relationship("ResearcherProfile", foreign_keys=[researcher_a_id], back_populates="collaborations")
    researcher_b = relationship("ResearcherProfile", foreign_keys=[researcher_b_id])

class ThesisRelationship(Base):
    __tablename__ = "thesis_relationships"
    id = Column(String, primary_key=True)
    source_thesis_id = Column(String, ForeignKey("ai_documents.id"), nullable=False)
    target_thesis_id = Column(String, ForeignKey("ai_documents.id"), nullable=False)
    relationship_type = Column(SAEnum(RelationshipType), nullable=False)
    confidence = Column(SAEnum(RelationshipConfidence), nullable=False)
    evidence = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    source_thesis = relationship("AIDocument", foreign_keys=[source_thesis_id])
    target_thesis = relationship("AIDocument", foreign_keys=[target_thesis_id])
