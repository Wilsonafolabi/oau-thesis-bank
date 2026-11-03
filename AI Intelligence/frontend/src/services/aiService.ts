/**
 * AI integration client.
 *
 * Every call goes through the single authenticated client in `lib/api`, so JWT
 * refresh, error parsing and the configured API base URL behave exactly as the
 * rest of the app. The browser never talks to the V2 service directly: Django
 * is the only entry point and it derives the actor from the JWT.
 *
 * Types below mirror the Django `ai_integration` contracts
 * (`AI_INTEGRATION_CONTRACT.md`). Fields the backend does not return are not
 * declared here.
 */

import { request } from '../lib/api';
import { ApiError } from '../lib/api';

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const getAIHealth = () => request<Record<string, unknown>>('ai/health/');

// ---------------------------------------------------------------------------
// Document ingestion
// ---------------------------------------------------------------------------

export interface ThesisIngestionMetadata {
  title?: string;
  author?: string;
  department?: string;
  faculty?: string;
  supervisor?: string;
  abstract?: string;
  year?: number | null;
}

export interface DocumentUploadResponse {
  document_id: string;
  job_id: string;
  status: string;
  message?: string;
}

export const ingestThesisPdf = (
  file: File,
  backendThesisId: number | string,
  metadata: ThesisIngestionMetadata = {},
) => {
  const form = new FormData();
  form.append('file', file);
  form.append('backend_thesis_id', String(backendThesisId));
  Object.entries(metadata).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, String(value));
    }
  });
  // access_level and backend_user_id are derived server-side; never send them.
  return request<DocumentUploadResponse>('ai/documents/upload/', {
    method: 'POST',
    body: form,
  });
};

export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage: string;
  message: string;
  result: Record<string, unknown> | null;
  error_message: string | null;
  error_stage: string | null;
  attempts: number;
  max_attempts: number;
}

export const getAIDocumentJob = (jobId: string) =>
  request<JobStatusResponse>(`ai/documents/jobs/${encodeURIComponent(jobId)}/`);

export interface DocumentPageText {
  page_number: number;
  text: string | null;
  char_offset_start: number | null;
  char_offset_end: number | null;
  is_scanned: boolean;
}

export interface DocumentTextResponse {
  document_id: string;
  backend_thesis_id: string;
  pages: DocumentPageText[];
  total_characters: number;
  total_pages: number;
}

export const getDocumentText = (internalDocumentId: string) =>
  request<DocumentTextResponse>(
    `ai/documents/${encodeURIComponent(internalDocumentId)}/text/`,
  );

export const deleteAIDocument = (internalDocumentId: string) =>
  request<{ detail: string }>(
    `ai/documents/${encodeURIComponent(internalDocumentId)}/`,
    { method: 'DELETE' },
  );

// ---------------------------------------------------------------------------
// RAG assistant
// ---------------------------------------------------------------------------

export type RagAbstentionReason =
  | 'no_evidence'
  | 'weak_evidence'
  | 'retrieval_degraded'
  | 'blocked_by_safety';

export interface RagCitation {
  chunk_id: string;
  document_id: string;
  backend_thesis_id: string;
  text_snippet: string;
  page_number: number | null;
  section: string | null;
  relevance_score: number;
}

export interface RagResponse {
  answer: string;
  citations: RagCitation[];
  confidence: number;
  /** Internal routing detail. Never rendered in the UI. */
  decision_engine: string;
  llm_tier: number;
  trace_id: string;
  request_id: string;
  insufficient_evidence: boolean;
  message: string | null;
  abstention_reason: RagAbstentionReason | null;
}

export const askResearchQuestion = (
  question: string,
  options: { documentIds?: string[]; topK?: number } = {},
) =>
  request<RagResponse>('ai/rag/ask/', {
    method: 'POST',
    json: {
      question,
      ...(options.documentIds?.length ? { document_ids: options.documentIds } : {}),
      ...(options.topK ? { top_k: options.topK } : {}),
    },
  });

export interface AssistantMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AssistantChatResponse {
  answer: string;
  /** Internal provider id. Never rendered in the UI. */
  provider: string;
  mode: string;
  message?: string | null;
}

/**
 * The browser chooses a tier, not a vendor. The backend only accepts its
 * configured provider ids, so the mapping stays here and never reaches the UI.
 */
export type AssistantModelTier = 'model-1' | 'model-2';

const PROVIDER_BY_TIER: Record<AssistantModelTier, 'deepseek' | 'groq'> = {
  'model-1': 'deepseek',
  'model-2': 'groq',
};

export const ASSISTANT_MODEL_LABELS: Record<AssistantModelTier, string> = {
  'model-1': 'Model 1',
  'model-2': 'Model 2',
};

export const askGeneralAssistant = (
  messages: AssistantMessage[],
  tier: AssistantModelTier = 'model-1',
) =>
  request<AssistantChatResponse>('ai/assistant/chat/', {
    method: 'POST',
    json: { messages, provider: PROVIDER_BY_TIER[tier] },
  });

// ---------------------------------------------------------------------------
// Thesis summaries
// ---------------------------------------------------------------------------

export type SummarySection =
  | 'research_problem'
  | 'objectives'
  | 'research_questions'
  | 'methodology'
  | 'dataset'
  | 'findings'
  | 'contributions'
  | 'limitations'
  | 'future_work';

export interface ThesisSummary {
  document_id: string;
  backend_thesis_id: string;
  user_id: string;
  title: string | null;
  abstract_summary: string | null;
  research_questions: string[];
  objectives: string[];
  methodology: string | null;
  findings: string[];
  limitations: string[];
  key_entities: string[];
  /** Fraction of the nine sections the source text actually supported. */
  confidence: number;
  /** Sections the thesis did not state. Nothing is invented to fill them. */
  missing_sections: SummarySection[];
}

export const getThesisSummary = (backendThesisId: string | number) =>
  request<ThesisSummary>(
    `ai/memory/thesis-summaries/${encodeURIComponent(String(backendThesisId))}/`,
  );

export const generateThesisSummary = (backendThesisId: string | number) =>
  request<ThesisSummary>('ai/memory/thesis-summaries/', {
    method: 'POST',
    json: { backend_thesis_id: String(backendThesisId), generate: true },
  });

/** Convenience wrapper used by the thesis summary screen. */
export const summarizeThesis = async (thesisId: number | string) => {
  const summary = await generateThesisSummary(thesisId);
  const parts = [
    summary.abstract_summary,
    summary.methodology ? `Methodology: ${summary.methodology}` : null,
    summary.findings.length ? `Findings: ${summary.findings.join('; ')}` : null,
    summary.limitations.length ? `Limitations: ${summary.limitations.join('; ')}` : null,
  ].filter(Boolean);
  return {
    summary: parts.join('\n\n') || undefined,
    sections: summary,
    message: summary.missing_sections.length
      ? `This thesis did not state: ${summary.missing_sections.join(', ').replace(/_/g, ' ')}.`
      : undefined,
  };
};

// ---------------------------------------------------------------------------
// Thesis Q&A (Stage 3.6)
// ---------------------------------------------------------------------------

export type ThesisQAScope = 'this_thesis' | 'public_theses';

export interface ThesisQACitation {
  chunk_id: string;
  document_id: string;
  backend_thesis_id: string;
  text_snippet: string;
  page_number: number | null;
  section: string | null;
  relevance_score: number;
}

export interface ThesisQAResponse {
  answer: string;
  citations: ThesisQACitation[];
  confidence: number;
  insufficient_evidence: boolean;
  message: string | null;
  trace_id: string;
}

export interface ThesisQARequest {
  backend_thesis_id: string;
  question: string;
  scope?: ThesisQAScope;
  top_k?: number;
}

export const askThesisQuestion = (body: ThesisQARequest) =>
  request<ThesisQAResponse>('ai/thesis-qa/ask/', {
    method: 'POST',
    json: {
      backend_thesis_id: body.backend_thesis_id,
      question: body.question,
      scope: body.scope ?? 'this_thesis',
      top_k: body.top_k ?? 5,
    },
  });

// ---------------------------------------------------------------------------
// Research gaps
// ---------------------------------------------------------------------------

export type GapSourceOrigin = 'author_stated' | 'system_inferred';

export interface ResearchGapCitation {
  chunk_id: string;
  document_id: string;
  backend_thesis_id: string;
  text_snippet: string;
  page_number: number | null;
  section: string | null;
  relevance_score: number;
}

export interface ResearchGap {
  gap_type: string;
  description: string;
  supporting_evidence: string;
  source_thesis_references: string[];
  page_numbers: (number | null)[];
  chunk_citations: ResearchGapCitation[];
  source_origin: GapSourceOrigin;
  explanation: string;
  suggested_research_direction: string;
  confidence: number;
}

export interface ResearchGapRequest {
  research_question: string;
  document_ids?: string[];
  top_k?: number;
}

export interface ResearchGapResponse {
  gaps: ResearchGap[];
  insufficient_evidence: boolean;
  confidence: number;
  decision_engine: string;
  llm_tier: number;
  trace_id: string;
  request_id: string;
  message?: string | null;
}

export const detectResearchGaps = (body: ResearchGapRequest) =>
  request<ResearchGapResponse>('ai/research-gaps/ask/', { method: 'POST', json: body });

export const detectGaps = async (topic?: string): Promise<ResearchGap[]> => {
  if (!topic) return [];
  const response = await detectResearchGaps({ research_question: topic });
  return response.gaps || [];
};

// ---------------------------------------------------------------------------
// Topic analysis
// ---------------------------------------------------------------------------

export interface TopicCount {
  name: string;
  document_count: number;
  thesis_ids: string[];
}

export interface TrendPoint {
  year: number | null;
  document_count: number;
}

export interface TopicAnalysisResponse {
  total_documents: number;
  analysed_documents: number;
  topics: TopicCount[];
  departments: TopicCount[];
  faculties: TopicCount[];
  years: TrendPoint[];
  limitations: string[];
}

export const analyzeTopics = (body: { max_documents?: number; max_topics?: number } = {}) =>
  request<TopicAnalysisResponse>('ai/topics/analyze/', { method: 'POST', json: body });

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

export type RecommendationType = 'existing_thesis';
export type RecommendationContextSource = 'request' | 'memory' | 'seed_thesis' | 'none';

export interface RecommendationEvidence {
  chunk_id: string;
  document_id: string;
  backend_thesis_id: string;
  text_snippet: string;
  page_number: number | null;
}

export interface Recommendation {
  recommendation_type: RecommendationType;
  title: string;
  backend_thesis_id: string | null;
  explanation: string;
  evidence: RecommendationEvidence[];
  /** Retrieval strength within this repository. Not quality or novelty. */
  evidence_strength: number;
  limitations: string[];
}

export interface RecommendationResponse {
  context_source: RecommendationContextSource;
  query: string;
  recommendations: Recommendation[];
  insufficient_evidence: boolean;
  message: string | null;
  limitations: string[];
}

export const getRecommendations = (
  body: { query?: string; seed_thesis_id?: string; top_k?: number } = {},
) => request<RecommendationResponse>('ai/recommendations/', { method: 'POST', json: body });

// ---------------------------------------------------------------------------
// Similarity
// ---------------------------------------------------------------------------

export type SimilarityMatchType = 'exact' | 'near_exact' | 'partial' | 'semantic';

export interface SimilarityMatch {
  match_type: SimilarityMatchType;
  score: number;
  document_id: string;
  backend_thesis_id: string;
  title: string | null;
  chunk_id: string;
  page_number: number | null;
  source_excerpt: string;
  submitted_excerpt: string;
}

export interface SimilarityResponse {
  input_mode: 'text';
  passages_scanned: number;
  chunks_scanned: number;
  matches: SimilarityMatch[];
  exact_matches: SimilarityMatch[];
  semantic_matches: SimilarityMatch[];
  limitations: string[];
}

export interface SimilarityCheckRequest {
  text: string;
  min_score?: number;
  max_matches?: number;
  exclude_document_ids?: string[];
  enable_semantic?: boolean;
}

// Status codes worth retrying: transient server / network issues, never 4xx client errors.
const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);

const sleep = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

export const checkSimilarity = async (
  body: SimilarityCheckRequest,
  { retries = 2, baseDelayMs = 500 }: { retries?: number; baseDelayMs?: number } = {},
): Promise<SimilarityResponse> => {
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await request<SimilarityResponse>('ai/similarity/check/', {
        method: 'POST',
        json: body,
      });
    } catch (err) {
      lastError = err;
      if (
        err instanceof ApiError &&
        RETRYABLE_STATUS_CODES.has(err.status) &&
        attempt < retries
      ) {
        await sleep(baseDelayMs * (attempt + 1));
        continue;
      }
      throw err;
    }
  }
  throw lastError;
};

export const checkSimilarityText = (
  text: string,
  excludeDocumentIds: string[] = [],
  topK = 20,
) =>
  checkSimilarity({
    text,
    max_matches: Math.max(1, Math.min(topK, 20)),
    ...(excludeDocumentIds.length ? { exclude_document_ids: excludeDocumentIds } : {}),
  });

// ---------------------------------------------------------------------------
// Plagiarism assessment (separate from similarity)
// ---------------------------------------------------------------------------

export type PlagiarismStatus =
  | 'attribution_present'
  | 'review_required'
  | 'no_significant_overlap';

export interface PlagiarismPassage {
  assessment: PlagiarismStatus;
  reason: string;
  quoted: boolean;
  cited: boolean;
  submitted_excerpt: string;
  matches: SimilarityMatch[];
}

export interface PlagiarismResponse {
  status: PlagiarismStatus;
  passages: PlagiarismPassage[];
  matched_source_count: number;
  limitations: string[];
  disclaimer: string;
}

export const assessPlagiarism = (body: {
  text: string;
  min_score?: number;
  exclude_document_ids?: string[];
}) => request<PlagiarismResponse>('ai/plagiarism/assess/', { method: 'POST', json: body });

// ---------------------------------------------------------------------------
// AI-writing detection
// ---------------------------------------------------------------------------

export type AIWritingStatus = 'ok' | 'insufficient_text' | 'unsupported_language' | 'unavailable';
export type AIWritingBand = 'likely_ai' | 'uncertain' | 'likely_human';

export interface AIWritingSegment {
  text: string;
  start_char: number;
  end_char: number;
  ai_probability: number;
  band: AIWritingBand;
}

export interface AIWritingDetectResponse {
  status: AIWritingStatus;
  assessment: AIWritingBand | null;
  ai_probability: number | null;
  confidence: number | null;
  segments: AIWritingSegment[];
  model_id: string | null;
  model_version: string | null;
  /** e.g. "temperature_scaled" when the model's published temperature applied. */
  calibration: string | null;
  limitations: string[];
  blocker: string | null;
  disclaimer: string;
}

export const detectAIWriting = (text: string) =>
  request<AIWritingDetectResponse>('ai/ai-writing/detect/', {
    method: 'POST',
    json: { text },
  });

/** Error code Django attaches when the detector itself cannot run. */
export const DETECTOR_UNAVAILABLE_CODE = 'detector_unavailable';

// ---------------------------------------------------------------------------
// Researcher memory
// ---------------------------------------------------------------------------

export interface MemoryEntry {
  id: string;
  user_id: string;
  memory_type: string;
  source: string;
  key: string;
  value: string;
  confidence: number;
  is_archived: boolean;
  source_document_id: string | null;
  source_chunk_id: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MemoryCreateRequest {
  key: string;
  value: string;
  memory_type?: string;
  source?: string;
  confidence?: number;
}

export interface MemoryUpdateRequest {
  value?: string;
  confidence?: number;
}

export interface MemoryResponse {
  entries: MemoryEntry[];
  total: number;
}

export interface MemoryRetrievalRequest {
  query: string;
  top_k?: number;
  memory_types?: string[];
}

export interface MemoryRetrievalResponse {
  entries: MemoryEntry[];
  total_found: number;
  query: string;
}

export interface MemoryPreferences {
  user_id: string;
  memory_enabled: boolean;
  semantic_retrieval_enabled: boolean;
  working_memory_window: number;
  memory_retention_days: number;
  auto_summarize: boolean;
}

export const retrieveMemories = (body: MemoryRetrievalRequest) =>
  request<MemoryRetrievalResponse>('ai/memory/retrieve/', { method: 'POST', json: body });

export const listMemories = (params?: {
  memory_type?: string;
  include_archived?: boolean;
  limit?: number;
}) => {
  const query = new URLSearchParams();
  if (params?.memory_type) query.set('memory_type', params.memory_type);
  if (params?.include_archived !== undefined) {
    query.set('include_archived', String(params.include_archived));
  }
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  const qs = query.toString();
  return request<MemoryResponse>(`ai/memory/${qs ? `?${qs}` : ''}`);
};

export const createMemory = (body: MemoryCreateRequest) =>
  request<MemoryEntry>('ai/memory/', { method: 'POST', json: body });

export const getMemory = (memoryId: string) =>
  request<MemoryEntry>(`ai/memory/${encodeURIComponent(memoryId)}/`);

export const updateMemory = (memoryId: string, body: MemoryUpdateRequest) =>
  request<MemoryEntry>(`ai/memory/${encodeURIComponent(memoryId)}/`, {
    method: 'PUT',
    json: body,
  });

export const deleteMemory = (memoryId: string) =>
  request<{ detail: string }>(`ai/memory/${encodeURIComponent(memoryId)}/`, {
    method: 'DELETE',
  });

export const getMemoryPreferences = () =>
  request<MemoryPreferences>('ai/memory/preferences/');

// ---------------------------------------------------------------------------
// Idea extension (RAG wrapper used by the idea screens)
// ---------------------------------------------------------------------------

export interface IdeaExtensionCitation {
  chunk_id: string;
  document_id: string;
  backend_thesis_id: string;
  text_snippet: string;
  page_number: number | null;
  section: string | null;
  relevance_score: number;
}

export interface IdeaExtensionResponse {
  extended_idea?: string;
  suggestions?: string;
  message?: string;
  citations: IdeaExtensionCitation[];
}

export const extendIdea = async (idea: string): Promise<IdeaExtensionResponse> => {
  const response = await request<RagResponse>('ai/rag/ask/', {
    method: 'POST',
    json: { question: `Expand on this research idea: ${idea}` },
  });
  return {
    extended_idea: response.answer || undefined,
    message: response.message ?? undefined,
    citations: response.citations.map((c) => ({
      chunk_id: c.chunk_id,
      document_id: c.document_id,
      backend_thesis_id: c.backend_thesis_id,
      text_snippet: c.text_snippet,
      page_number: c.page_number,
      section: c.section,
      relevance_score: c.relevance_score,
    })),
  };
};
