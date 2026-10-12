import { getAccessToken } from '../lib/auth';

const AI_BASE_URL = 'http://127.0.0.1:8888/api';

export interface Recommendation { thesis_id: string; score?: number; model_used?: string; source?: string; }
export interface ResearchGap { topic_id?: number; topic_name: string; document_count?: number; representative_keywords?: string[]; thesis_ids?: string[]; method?: string; interpretation?: string; }
export interface SimilarityReport { status: string; threshold_used?: number; pages_scanned?: number; chunks_scanned?: number; flagged_chunks_count?: number; flagged_chunks?: Array<{ source_page: number; document_id: string; matched_page: number; similarity_score: number; text_preview: string; }>; message?: string; }
export interface CitationSource { document_id: string; page: number; similarity: number; }
export interface RagResponse { answer?: string; message?: string; citations?: string[]; sources?: CitationSource[]; decision_engine?: string; confidence?: number; }
export interface IdeaExtensionResponse { extended_idea?: string; suggestions?: string; message?: string; }

async function aiRequest<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set('Accept', 'application/json');
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.json !== undefined) {
    headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(init.json);
  }
  const url = `${AI_BASE_URL}/${path.replace(/^\/+/, '')}`;
  init.headers = headers;
  const response = await fetch(url, init);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`AI Backend Error ${response.status}: ${errorText}`);
  }
  return response.json();
}

export async function getAIHealth() { return aiRequest<Record<string, unknown>>('v1/health'); }

export async function askResearchQuestion(query: string) {
  const res = await aiRequest<RagResponse>('v1/rag/ask', { method: 'POST', json: { question: query } });
  if (res.sources && Array.isArray(res.sources)) {
    res.sources = res.sources.map(s => ({ document_id: s.document_id || 'unknown', page: typeof s.page === 'number' ? s.page : 0, similarity: typeof s.similarity === 'number' ? s.similarity : 0 }));
  }
  return res;
}

export async function summarizeThesis(thesisId: number) {
  return aiRequest<{ summary?: string; message?: string }>('v1/rag/ask', { method: 'POST', json: { question: `Summarize thesis ${thesisId}` } });
}

export async function checkSimilarity(file: File): Promise<SimilarityReport> {
  const form = new FormData();
  form.append('file', file);
  const uploadRes = await aiRequest<{ job_id: string }>('v1/documents/upload', { method: 'POST', body: form });
  return { status: 'processing', message: `Job ${uploadRes.job_id} queued for similarity check.` };
}

export async function checkProposal(proposalText: string, threshold = 0.8) {
  return aiRequest<{ score?: number; feedback?: string; message?: string }>('v1/rag/ask', { method: 'POST', json: { question: `Evaluate this proposal against existing theses: ${proposalText}` } });
}

export async function detectGaps(topic?: string): Promise<ResearchGap[]> {
  const query = topic ? `?topic=${encodeURIComponent(topic)}` : '';
  const res = await aiRequest<ResearchGap[] | { gaps: ResearchGap[] }>(`v1/research-gaps${query}`);
  return Array.isArray(res) ? res : (res.gaps || []);
}

export async function extendIdea(idea: string) {
  return aiRequest<IdeaExtensionResponse>('v1/rag/ask', { method: 'POST', json: { question: `Expand on this research idea: ${idea}` } });
}

export async function getRecommendations(userId: string, topK = 5): Promise<Recommendation[]> {
  return aiRequest<Recommendation[]>(`v1/intelligence/researchers?limit=${topK}`);
}

export async function logInteraction(userId: string, thesisId: string, eventType: string) {
  return aiRequest<Record<string, unknown>>('v1/health'); 
}

export async function getResearchNetwork() {
  return aiRequest<{ nodes: unknown[]; edges: unknown[] }>('v1/intelligence/researchers');
}
