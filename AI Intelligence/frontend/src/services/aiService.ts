const AI_API_BASE = (
  import.meta.env.VITE_AI_API_BASE_URL || 'http://127.0.0.1:8888/api/ai'
).replace(/\/$/, '');

export interface Recommendation {
  thesis_id: string;
  score?: number;
  model_used?: string;
}

export interface ResearchGap {
  topic_id: number;
  topic_name: string;
  document_count: number;
  representative_keywords: string[];
  thesis_ids?: string[];
  method?: string;
  interpretation?: string;
}

export interface SimilarityReport {
  status: string;
  threshold_used?: number;
  pages_scanned?: number;
  chunks_scanned?: number;
  flagged_chunks_count?: number;
  flagged_chunks?: Array<{
    source_page: number;
    document_id: string;
    matched_page: number;
    similarity_score: number;
    text_preview: string;
  }>;
  message?: string;
}

async function parseResponse(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : `AI service returned HTTP ${response.status}`,
    );
  }
  return data;
}

export async function getAIHealth() {
  return parseResponse(await fetch(`${AI_API_BASE}/health`));
}

export async function askResearchQuestion(query: string) {
  return parseResponse(await fetch(`${AI_API_BASE}/rag-query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  }));
}

export async function summarizeThesis(thesisId: number) {
  return parseResponse(await fetch(`${AI_API_BASE}/summarize?thesis_id=${encodeURIComponent(thesisId)}`, {
    method: 'POST',
  }));
}

export async function checkSimilarity(file: File): Promise<SimilarityReport> {
  const body = new FormData();
  body.append('file', file);
  return parseResponse(await fetch(`${AI_API_BASE}/check-similarity`, {
    method: 'POST',
    body,
  }));
}

export async function checkProposal(proposalText: string, threshold = 0.8) {
  return parseResponse(await fetch(`${AI_API_BASE}/check-proposal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proposal_text: proposalText, threshold }),
  }));
}

export async function detectGaps(topic?: string): Promise<ResearchGap[]> {
  const query = topic ? `?topic=${encodeURIComponent(topic)}` : '';
  const data = await parseResponse(await fetch(`${AI_API_BASE}/detect-gaps${query}`));
  return data.gaps || [];
}

export async function extendIdea(idea: string) {
  return parseResponse(await fetch(`${AI_API_BASE}/idea-extension`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idea }),
  }));
}

export async function getRecommendations(userId: string, topK = 5): Promise<Recommendation[]> {
  const data = await parseResponse(
    await fetch(`${AI_API_BASE}/recommend?user_id=${encodeURIComponent(userId)}&top_k=${topK}`),
  );
  return data.recommendations || [];
}

export async function logInteraction(userId: string, thesisId: string, eventType: string) {
  return parseResponse(await fetch(`${AI_API_BASE}/interact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      thesis_id: thesisId,
      event_type: eventType,
    }),
  }));
}

export async function getResearchNetwork() {
  return parseResponse(await fetch(`${AI_API_BASE}/network`));
}

export async function addResearchNetworkEdge(payload: {
  researcher_a: string;
  researcher_b: string;
  basis_document_id: string;
  basis_type?: string;
}) {
  return parseResponse(await fetch(`${AI_API_BASE}/network/add-edge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
}
