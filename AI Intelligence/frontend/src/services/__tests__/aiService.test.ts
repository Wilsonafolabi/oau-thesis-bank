import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as aiService from '../aiService';
import { ApiError } from '../../lib/api';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

describe('AI service — Django contracts', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  const lastCall = () => {
    const [url, init] = fetchSpy.mock.calls[fetchSpy.mock.calls.length - 1] as [
      string,
      RequestInit,
    ];
    return { url: String(url), init };
  };

  it('routes RAG questions through the authenticated Django endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        answer: 'Grounded answer',
        citations: [
          {
            chunk_id: 'c1',
            document_id: 'd1',
            backend_thesis_id: '7',
            text_snippet: 'evidence',
            page_number: 3,
            section: null,
            relevance_score: 0.5,
          },
        ],
        confidence: 0.9,
        decision_engine: 'internal',
        llm_tier: 1,
        trace_id: 't',
        request_id: 'r',
        insufficient_evidence: false,
        message: null,
        abstention_reason: null,
      }),
    );

    const result = await aiService.askResearchQuestion('What is machine learning?');

    const { url, init } = lastCall();
    expect(url).toContain('ai/rag/ask/');
    expect(init.method).toBe('POST');
    expect(result.citations[0].backend_thesis_id).toBe('7');
    expect(result.abstention_reason).toBeNull();
  });

  it('passes abstention states through unchanged', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        answer: '',
        citations: [],
        confidence: 0,
        decision_engine: 'internal',
        llm_tier: 1,
        trace_id: 't',
        request_id: 'r',
        insufficient_evidence: true,
        message: 'Semantic retrieval is unavailable.',
        abstention_reason: 'retrieval_degraded',
      }),
    );

    const result = await aiService.askResearchQuestion('anything');

    expect(result.insufficient_evidence).toBe(true);
    expect(result.abstention_reason).toBe('retrieval_degraded');
    expect(result.citations).toEqual([]);
  });

  it('uploads the PDF against its thesis id without sending access_level', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({ document_id: 'doc-1', job_id: 'job-1', status: 'pending' }),
    );

    const file = new File(['%PDF-1.7'], 'thesis.pdf', { type: 'application/pdf' });
    const result = await aiService.ingestThesisPdf(file, 42, { title: 'T' });

    const { url, init } = lastCall();
    const body = init.body as FormData;
    expect(url).toContain('ai/documents/upload/');
    expect(body.get('backend_thesis_id')).toBe('42');
    expect(body.get('access_level')).toBeNull();
    expect(body.get('backend_user_id')).toBeNull();
    expect(result.job_id).toBe('job-1');
  });

  it('reads job status using the published completed vocabulary', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        job_id: 'job-1',
        status: 'completed',
        stage: 'complete',
        message: 'ok',
        result: null,
        error_message: null,
        error_stage: null,
        attempts: 1,
        max_attempts: 3,
      }),
    );

    const result = await aiService.getAIDocumentJob('job-1');

    expect(lastCall().url).toContain('ai/documents/jobs/job-1/');
    expect(result.status).toBe('completed');
  });

  it('surfaces authentication expiry as a 401 ApiError', async () => {
    fetchSpy.mockResolvedValueOnce(json({ detail: 'Authentication required.' }, 401));

    await expect(aiService.askResearchQuestion('x')).rejects.toMatchObject({
      status: 401,
    });
  });

  it('surfaces access denial as a 403 ApiError', async () => {
    fetchSpy.mockResolvedValueOnce(json({ detail: 'You do not have access.' }, 403));

    const error = await aiService
      .checkSimilarity({ text: 'some text' })
      .catch((err: unknown) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(403);
  });

  it('surfaces the detector 503 with its explanation and no score', async () => {
    fetchSpy.mockResolvedValueOnce(
      json(
        {
          error: 'AI Service Error',
          detail: 'Weights are not present locally.',
          code: 'detector_unavailable',
        },
        503,
      ),
    );

    const error = await aiService
      .detectAIWriting('some text')
      .catch((err: unknown) => err);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).detail).toContain('Weights are not present');
  });

  it('maps the assistant tier to a provider without exposing names to callers', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({ answer: 'General', provider: 'internal', mode: 'general' }),
    );

    await aiService.askGeneralAssistant([{ role: 'user', content: 'hi' }], 'model-2');

    const { url, init } = lastCall();
    expect(url).toContain('ai/assistant/chat/');
    expect((init.body as string).includes('"provider":"groq"')).toBe(true);
    expect(aiService.ASSISTANT_MODEL_LABELS['model-2']).toBe('Model 2');
  });

  it('sends similarity checks to the Django route with a bounded match count', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        input_mode: 'text',
        passages_scanned: 1,
        chunks_scanned: 4,
        matches: [],
        exact_matches: [],
        semantic_matches: [],
        limitations: ['lexical only'],
      }),
    );

    await aiService.checkSimilarityText('idea text', ['d1'], 99);

    const { url, init } = lastCall();
    expect(url).toContain('ai/similarity/check/');
    expect((init.body as string).includes('"max_matches":20')).toBe(true);
    expect((init.body as string).includes('"exclude_document_ids":["d1"]')).toBe(true);
  });

  it('keeps plagiarism assessment on its own endpoint', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        status: 'review_required',
        passages: [],
        matched_source_count: 1,
        limitations: [],
        disclaimer: 'Not a finding of plagiarism.',
      }),
    );

    const result = await aiService.assessPlagiarism({ text: 'text' });

    expect(lastCall().url).toContain('ai/plagiarism/assess/');
    expect(result.status).toBe('review_required');
  });

  it('requests topic analysis from the Django aggregation route', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        total_documents: 2,
        analysed_documents: 2,
        topics: [{ name: 'rotation', document_count: 2, thesis_ids: ['1', '2'] }],
        departments: [],
        faculties: [],
        years: [{ year: 2023, document_count: 2 }],
        limitations: [],
      }),
    );

    const result = await aiService.analyzeTopics({ max_documents: 50 });

    expect(lastCall().url).toContain('ai/topics/analyze/');
    expect(result.topics[0].name).toBe('rotation');
  });

  it('requests recommendations and preserves the abstention message', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        context_source: 'none',
        query: '',
        recommendations: [],
        insufficient_evidence: true,
        message: 'No research context was supplied.',
        limitations: [],
      }),
    );

    const result = await aiService.getRecommendations();

    expect(lastCall().url).toContain('ai/recommendations/');
    expect(result.insufficient_evidence).toBe(true);
  });

  it('generates thesis summaries with generate: true', async () => {
    fetchSpy.mockResolvedValueOnce(
      json({
        document_id: 'd1',
        backend_thesis_id: '5',
        user_id: '1',
        title: 'Soil',
        abstract_summary: 'Research problem: low yields',
        research_questions: [],
        objectives: [],
        methodology: null,
        findings: [],
        limitations: [],
        key_entities: [],
        confidence: 0.11,
        missing_sections: ['objectives', 'methodology'],
      }),
    );

    const summary = await aiService.generateThesisSummary(5);

    const { url, init } = lastCall();
    expect(url).toContain('ai/memory/thesis-summaries/');
    expect((init.body as string).includes('"generate":true')).toBe(true);
    expect(summary.missing_sections).toContain('methodology');
  });

  it('no longer calls the V2 service directly', () => {
    // The removed V1/V2 direct callers must not come back.
    expect((aiService as Record<string, unknown>).checkSimilarityPdf).toBeUndefined();
    expect((aiService as Record<string, unknown>).getWorkingMemory).toBeUndefined();
    expect((aiService as Record<string, unknown>).getResearchNetwork).toBeUndefined();
  });
});
