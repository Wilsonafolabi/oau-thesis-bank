# PHASE 3 IMPLEMENTATION CONTRACT — V2
**Status:** AMENDED
**Date:** October 28, 2026
**Authority:** This document is the single source of truth for all Phase 3 V2 interfaces.
It amends the original frozen contract at the repository root to reflect the
approved model-routing and provider decisions.

## 1. CROSS-CUTTING CONTRACTS

### 1.1 Security & Access-Control Propagation
- Access classification must be evaluated before retrieval and after generation.
- Every request must carry an actor_context containing user_id, roles, and department.
- The AI service must not trust browser-supplied roles or user IDs. Django remains
  the authority for authentication, user roles, thesis permissions, and access to
  private thesis content.

### 1.2 Telemetry Contract
- All AI calls must be observable via TelemetryEvent.
- Every request must generate a trace_id (UUIDv4) passed through all components.

### 1.3 Error Contract
- No silent failures. All errors must conform to Phase3Error.
- Retryable flag indicates if operation can be safely retried.

### 1.4 Confidence Conventions
- Scale: 0.0 to 1.0. >= 0.85 High, 0.50-0.84 Medium, < 0.50 Low (trigger fallback).
- Confidence is separate from evidence-grounding validation. Model self-reported
  confidence is not treated as reliable without independent validation.

### 1.5 LLM Routing Contract (JEV) — V2 AMENDED
- **Primary: DeepSeek** (reasoning and answer generation for the main
  research-agent workflow).
- **Groq** is reserved for explicitly designated smaller tasks only. It is not a
  fallback for DeepSeek and must not silently take over primary-model tasks.
- **No automatic provider fallback.** Provider failure must not trigger a switch
  to another model. Use bounded retries only where explicitly justified, without
  changing providers. If the required provider is unavailable, return a structured
  error.
- Tier 3 (offline/PII-sensitive) routing decisions are reserved for explicit
  configuration and are not implied by any provider being "local" or "private"
  without evidence.

## 2. CORE DATA SCHEMAS

### 2.1 Base Provenance Schema
class Provenance(BaseModel):
    document_id: str
    source_file: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    access_classification: str = "public"
    created_at: datetime

### 3.1 Document Intelligence Schemas
class Document(BaseModel):
    id: str; title: str; source_file: str; file_hash: str
    total_pages: int; access_classification: str; metadata: Dict[str, Any]

class DocumentPage(BaseModel):
    document_id: str; page_number: int; is_scanned: bool
    text_content: str; image_path: Optional[str]; provenance: Provenance

class Chunk(BaseModel):
    chunk_id: str; document_id: str; section_id: Optional[str]
    text: str; token_count: int; overlap_count: int; provenance: Provenance

### 3.2 Embeddings Schema
class Embedding(BaseModel):
    chunk_id: str; document_id: str; vector: List[float]
    model_name: str; model_version: str; provenance: Provenance

### 3.3 Hybrid Search Schemas
class SearchResult(BaseModel):
    chunk_id: str; document_id: str
    score_bm25: float; score_dense: float; score_hybrid: float
    text_snippet: str; provenance: Provenance

class RerankedResult(BaseModel):
    chunk_id: str; document_id: str
    original_hybrid_score: float; rerank_score: float; final_score: float
    text_snippet: str; provenance: Provenance

### 3.4 RAG Schemas
class Evidence(BaseModel):
    chunk_id: str; document_id: str; text: str; relevance_score: float; provenance: Provenance

class GroundingDecision(BaseModel):
    claim_id: str; is_grounded: bool; confidence: float
    supporting_evidence_ids: List[str]; verification_method: str

### 3.5 Research Intelligence Schemas
class SimilarityResult(BaseModel):
    source_document_id: str; target_document_id: str; similarity_score: float
    is_plagiarism_suspect: bool; provenance: Provenance

class ResearchGap(BaseModel):
    gap_id: str; topic_name: str; description: str
    document_count: int; representative_keywords: List[str]; confidence: float

### 3.6 Researcher Intelligence Schemas
class Researcher(BaseModel):
    researcher_id: str; name: str; department: str; topics: List[str]; role: str

class ResearcherEdge(BaseModel):
    source_researcher_id: str; target_researcher_id: str
    edge_type: str; confidence: float; provenance: Provenance

### 3.7 Telemetry Schema
class TelemetryEvent(BaseModel):
    trace_id: str; component: str; event_type: str; timestamp: datetime
    duration_ms: Optional[float]; model_provider: Optional[str]; llm_tier: Optional[int]

## 3. ERROR CONTRACT
class Phase3Error(Exception):
    code: str; message: str; component: str; retryable: bool; trace_id: str

## 4. IMPLEMENTATION DIRECTIVES
1. No Mocks: All schemas must be backed by real Pydantic models.
2. Provenance First: Text derived from a document MUST return the Provenance object.
3. Strict Typing: All interfaces between components must use these exact Pydantic models.
4. Telemetry Injection: Every component must wrap execution in a telemetry context manager.
