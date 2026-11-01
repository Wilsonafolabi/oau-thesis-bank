"""API request/response schemas for V2 endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentUploadRequest(BaseModel):
    backend_thesis_id: str = Field(..., description="Phase 2 thesis ID")
    backend_user_id: str = Field(..., description="Phase 2 user ID")
    access_level: str = Field(
        default="private",
        description="public | restricted | private",
    )
    thesis_metadata: Optional[dict] = Field(
        default=None, description="Optional thesis metadata"
    )


class DocumentUploadResponse(BaseModel):
    document_id: str
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: Optional[str]
    message: Optional[str]
    result: Optional[dict] = None
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    attempts: int
    max_attempts: int


class RAGRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = Field(
        default=None, description="Optional list of document/backend_thesis IDs to search"
    )
    top_k: int = Field(default=5, ge=1, le=20)


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int]
    section: Optional[str]
    relevance_score: float


class RAGResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    confidence: float
    decision_engine: str
    llm_tier: int
    trace_id: str
    request_id: str
    insufficient_evidence: bool = False
    message: Optional[str] = None
    abstention_reason: Optional[str] = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    component: str
    retryable: bool
    trace_id: Optional[str] = None


class ResearchGapCitationSchema(BaseModel):
    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int]
    section: Optional[str]
    relevance_score: float


class ResearchGapSchema(BaseModel):
    gap_type: str
    description: str
    supporting_evidence: str
    source_thesis_references: List[str]
    page_numbers: List[Optional[int]]
    chunk_citations: List[ResearchGapCitationSchema]
    source_origin: str
    explanation: str
    suggested_research_direction: str
    confidence: float


class ResearchGapRequest(BaseModel):
    research_question: str = Field(..., min_length=1)
    document_ids: Optional[List[str]] = Field(
        default=None, description="Optional list of document/backend_thesis IDs to search"
    )
    top_k: int = Field(default=10, ge=1, le=20)


class ResearchGapResponse(BaseModel):
    gaps: List[ResearchGapSchema]
    insufficient_evidence: bool
    confidence: float
    decision_engine: str
    llm_tier: int
    trace_id: str
    request_id: str
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Researcher Memory Schemas (Phase 5.3)
# ---------------------------------------------------------------------------

class MemoryEntrySchema(BaseModel):
    id: str
    user_id: str
    memory_type: str
    source: str
    key: str
    value: str
    confidence: float
    is_archived: bool
    source_document_id: Optional[str] = None
    source_chunk_id: Optional[str] = None
    provenance: Dict[str, Any] = {}
    created_at: str
    updated_at: str


class MemoryCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Memory key identifier")
    value: str = Field(..., min_length=1, description="Memory value content")
    memory_type: str = Field(
        default="profile",
        description="profile | research_interest | research_objective | methodology_preference | supervisor_info",
    )
    source: str = Field(
        default="system_inferred",
        description="author_stated | system_inferred | extracted_from_conversation | extracted_from_document",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryUpdateRequest(BaseModel):
    value: Optional[str] = Field(None, min_length=1)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class MemoryResponse(BaseModel):
    entries: List[MemoryEntrySchema]
    total: int


class MemoryRetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=20)
    memory_types: Optional[List[str]] = Field(
        default=None,
        description="Optional filter by memory type",
    )


class MemoryRetrievalResponse(BaseModel):
    entries: List[MemoryEntrySchema]
    total_found: int
    query: str


class ThesisSummarySchema(BaseModel):
    document_id: str
    backend_thesis_id: str
    user_id: str
    title: Optional[str]
    abstract_summary: Optional[str]
    research_questions: List[str]
    objectives: List[str]
    methodology: Optional[str]
    findings: List[str]
    limitations: List[str]
    key_entities: List[str]
    confidence: float
    missing_sections: List[str] = []


class ThesisSummaryCreateRequest(BaseModel):
    backend_thesis_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    abstract_summary: Optional[str] = None
    research_questions: List[str] = []
    objectives: List[str] = []
    methodology: Optional[str] = None
    findings: List[str] = []
    limitations: List[str] = []
    key_entities: List[str] = []
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # When true the summary is generated from the thesis's own extracted text
    # and every content field in the request is ignored.
    generate: bool = False


class WorkingMemoryExchangeSchema(BaseModel):
    id: str
    user_id: str
    exchange_type: str
    content: str
    summary: Optional[str]
    unresolved_questions: List[str]
    decisions: List[str]
    current_tasks: List[str]
    is_summarized: bool
    created_at: str


class MemoryPreferencesSchema(BaseModel):
    user_id: str
    memory_enabled: bool = True
    semantic_retrieval_enabled: bool = True
    working_memory_window: int = Field(default=5, ge=1, le=20)
    memory_retention_days: int = Field(default=90, ge=1, le=365)
    auto_summarize: bool = True


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    max_iterations: int = Field(default=5, ge=1, le=10)


class AgentAskResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = []
    confidence: float
    insufficient_evidence: bool = False
    status: str
    iteration_count: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Working memory (create + context)
# ---------------------------------------------------------------------------


class WorkingMemoryCreateRequest(BaseModel):
    exchange_type: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    unresolved_questions: List[str] = []
    decisions: List[str] = []
    current_tasks: List[str] = []


class WorkingMemoryCreateResponse(BaseModel):
    exchange_id: str
    user_id: str


class WorkingMemoryContextResponse(BaseModel):
    user_id: str
    context: str


# ---------------------------------------------------------------------------
# Entities and relationships (researcher network)
# ---------------------------------------------------------------------------


class EntityExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


class EntitySchema(BaseModel):
    id: str
    user_id: str
    entity_type: str
    entity_name: str
    normalized_name: str
    description: Optional[str] = None
    confidence: str
    occurrence_count: int


class EntityExtractResponse(BaseModel):
    entities: List[Dict[str, Any]]
    total: int


class EntityListResponse(BaseModel):
    entities: List[EntitySchema]
    total: int


class EntityRelationshipCreateRequest(BaseModel):
    source_entity_id: str = Field(..., min_length=1)
    target_entity_id: str = Field(..., min_length=1)
    relationship_type: str = Field(..., min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EntityRelationshipSchema(BaseModel):
    id: str
    user_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    confidence: str


class EntityRelationshipCreateResponse(BaseModel):
    relationship_id: str


class EntityRelationshipListResponse(BaseModel):
    relationships: List[EntityRelationshipSchema]
    total: int


# ---------------------------------------------------------------------------
# General-knowledge assistant
# ---------------------------------------------------------------------------


class AssistantChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str = Field(..., min_length=1)


class AssistantChatRequest(BaseModel):
    messages: List[AssistantChatMessage] = Field(..., min_length=1)
    provider: str = Field(default="deepseek", description="deepseek | groq")


class AssistantChatResponse(BaseModel):
    answer: str
    provider: str
    mode: str = "general"
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Topic discovery and research recommendations (P4)
# ---------------------------------------------------------------------------


class TopicAnalysisRequest(BaseModel):
    max_documents: int = Field(default=200, ge=1, le=500)
    max_topics: int = Field(default=25, ge=1, le=50)


class TopicCountSchema(BaseModel):
    name: str
    document_count: int
    thesis_ids: List[str] = []


class TrendPointSchema(BaseModel):
    year: Optional[int] = None
    document_count: int


class TopicAnalysisResponse(BaseModel):
    total_documents: int
    analysed_documents: int
    topics: List[TopicCountSchema]
    departments: List[TopicCountSchema]
    faculties: List[TopicCountSchema]
    years: List[TrendPointSchema]
    limitations: List[str] = []


class RecommendationRequest(BaseModel):
    query: Optional[str] = Field(default=None, max_length=2000)
    seed_thesis_id: Optional[str] = Field(default=None, max_length=64)
    top_k: int = Field(default=5, ge=1, le=20)


class RecommendationEvidenceSchema(BaseModel):
    chunk_id: str
    document_id: str
    backend_thesis_id: str
    text_snippet: str
    page_number: Optional[int] = None


class RecommendationSchema(BaseModel):
    recommendation_type: str
    title: str
    backend_thesis_id: Optional[str] = None
    explanation: str
    evidence: List[RecommendationEvidenceSchema]
    evidence_strength: float
    limitations: List[str] = []


class RecommendationResponseSchema(BaseModel):
    context_source: str
    query: str
    recommendations: List[RecommendationSchema]
    insufficient_evidence: bool
    message: Optional[str] = None
    limitations: List[str] = []


# ---------------------------------------------------------------------------
# Similarity, plagiarism assessment and AI-writing detection (P5)
# ---------------------------------------------------------------------------


class SimilarityCheckRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=100_000)
    min_score: float = Field(default=0.25, ge=0.0, le=1.0)
    max_matches: int = Field(default=20, ge=1, le=20)
    exclude_document_ids: List[str] = []
    enable_semantic: bool = True


class SimilarityMatchSchema(BaseModel):
    match_type: str
    score: float
    document_id: str
    backend_thesis_id: str
    title: Optional[str] = None
    chunk_id: str
    page_number: Optional[int] = None
    source_excerpt: str
    submitted_excerpt: str


class SimilarityResponseSchema(BaseModel):
    input_mode: str
    passages_scanned: int
    chunks_scanned: int
    matches: List[SimilarityMatchSchema]
    exact_matches: List[SimilarityMatchSchema]
    semantic_matches: List[SimilarityMatchSchema]
    limitations: List[str] = []


class PlagiarismAssessRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=100_000)
    min_score: float = Field(default=0.25, ge=0.0, le=1.0)
    exclude_document_ids: List[str] = []


class PlagiarismPassageSchema(BaseModel):
    assessment: str
    reason: str
    quoted: bool
    cited: bool
    submitted_excerpt: str
    matches: List[SimilarityMatchSchema]


class PlagiarismResponseSchema(BaseModel):
    status: str
    passages: List[PlagiarismPassageSchema]
    matched_source_count: int
    limitations: List[str] = []
    disclaimer: str


class AIWritingDetectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)


class AIWritingSegmentSchema(BaseModel):
    text: str
    start_char: int
    end_char: int
    ai_probability: float
    band: str


class AIWritingResponseSchema(BaseModel):
    status: str
    assessment: Optional[str] = None
    ai_probability: Optional[float] = None
    confidence: Optional[float] = None
    segments: List[AIWritingSegmentSchema] = []
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    calibration: Optional[str] = None
    limitations: List[str] = []
    blocker: Optional[str] = None
    disclaimer: str
