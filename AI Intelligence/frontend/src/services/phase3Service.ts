import { request } from '../lib/api';
import type { JobResponse, RagAskRequest, RagAskResponse, ResearcherProfilePhase3, EvaluationStatus } from '../types/api';

/**
 * Phase 3 Backend Services
 * Connects to the real FastAPI backend (/api/v1/...)
 * Uses the existing 'request' helper to automatically handle auth tokens, retries, and error parsing.
 * NO hardcoded mocks or fake data.
 */

export const uploadDocumentPhase3 = (form: FormData) => 
  request<{ document_id: string; job_id: string; status: string }>('v1/documents/upload', { method: 'POST', body: form });

export const getJobStatusPhase3 = (jobId: string) => 
  request<JobResponse>(`v1/documents/jobs/${jobId}`);

export const askRagQuestionPhase3 = (payload: RagAskRequest) => 
  request<RagAskResponse>('v1/rag/ask', { method: 'POST', json: payload });

export const getResearchersPhase3 = (limit = 10, offset = 0) => 
  request<ResearcherProfilePhase3[]>(`v1/intelligence/researchers?limit=${limit}&offset=${offset}`);

export const getEvaluationStatusPhase3 = () => 
  request<EvaluationStatus>('v1/evaluations/status');

export const getHealthPhase3 = () => 
  request<Record<string, unknown>>('v1/health');
