import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as aiService from '../aiService';

describe('Phase 3 AI Service Integration', () => {
  let fetchSpy: any;

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock global fetch
    fetchSpy = vi.spyOn(global, 'fetch').mockImplementation((url: any, init: any) => {
      return Promise.resolve({
        ok: true,
        json: () => {
          if (String(url).includes('v1/rag/ask')) {
            return Promise.resolve({ answer: 'Real answer', citations: ['doc_1'], decision_engine: 'laya', confidence: 0.95 });
          }
          if (String(url).includes('v1/research-gaps')) {
            return Promise.resolve([{ topic_name: 'AI in Agriculture' }]);
          }
          return Promise.resolve({});
        },
        text: () => Promise.resolve('')
      } as Response);
    });
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('routes RAG questions through the authenticated backend', async () => {
    const result = await aiService.askResearchQuestion('What is machine learning?');
    
    // Verify the request was made to the correct endpoint with POST method
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('v1/rag/ask'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.any(Headers)
      })
    );
    
    // Verify the response is parsed correctly
    expect(result.answer).toBe('Real answer');
    expect(result.citations).toContain('doc_1');
    expect(result.decision_engine).toBe('laya');
  });

  it('handles backend unavailability truthfully without faking success', async () => {
    // Override fetch mock for this specific test to simulate a 503 error
    fetchSpy.mockImplementationOnce(() => 
      Promise.resolve({
        ok: false,
        status: 503,
        text: () => Promise.resolve('Service Unavailable')
      } as Response)
    );

    await expect(aiService.askResearchQuestion('test')).rejects.toThrow('AI Backend Error 503: Service Unavailable');
  });

  it('routes research gap detection to the real backend', async () => {
    const gaps = await aiService.detectGaps('Agriculture');
    
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('v1/research-gaps?topic=Agriculture'),
      expect.any(Object)
    );
    
    expect(gaps[0].topic_name).toBe('AI in Agriculture');
  });
});
