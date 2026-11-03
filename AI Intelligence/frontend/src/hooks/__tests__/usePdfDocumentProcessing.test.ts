/**
 * Unit tests for the shared PDF document processing hook.
 *
 * All backend calls are mocked. These tests verify the hook orchestrates
 * upload → poll → extract → analyze → cleanup correctly, without any
 * dependency on a live Django or V2 service.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePdfDocumentProcessing } from '../usePdfDocumentProcessing';

vi.mock('../../services/aiService', () => ({
  ingestThesisPdf: vi.fn(),
  getAIDocumentJob: vi.fn(),
  getDocumentText: vi.fn(),
  deleteAIDocument: vi.fn(),
}));

import {
  ingestThesisPdf,
  getAIDocumentJob,
  getDocumentText,
  deleteAIDocument,
} from '../../services/aiService';

const mockIngest = ingestThesisPdf as ReturnType<typeof vi.fn>;
const mockJob = getAIDocumentJob as ReturnType<typeof vi.fn>;
const mockText = getDocumentText as ReturnType<typeof vi.fn>;
const mockDelete = deleteAIDocument as ReturnType<typeof vi.fn>;

const defaultAnalysisFn = vi.fn().mockResolvedValue({ analysis: 'done' });

beforeEach(() => {
  vi.clearAllMocks();
  defaultAnalysisFn.mockResolvedValue({ analysis: 'done' });
  mockIngest.mockResolvedValue({
    document_id: 'doc-1',
    job_id: 'job-1',
    status: 'pending',
  });
  mockJob.mockResolvedValue({
    job_id: 'job-1',
    status: 'completed',
    stage: 'complete',
    message: 'ok',
    result: null,
    error_message: null,
    error_stage: null,
    attempts: 1,
    max_attempts: 3,
  });
  mockText.mockResolvedValue({
    document_id: 'doc-1',
    backend_thesis_id: 'tmp-pdf-abc',
    pages: [
      {
        page_number: 1,
        text: 'Page one text.',
        char_offset_start: 0,
        char_offset_end: 14,
        is_scanned: false,
      },
      {
        page_number: 2,
        text: 'Page two text.',
        char_offset_start: 15,
        char_offset_end: 29,
        is_scanned: false,
      },
    ],
    total_characters: 28,
    total_pages: 2,
  });
  mockDelete.mockResolvedValue({ detail: 'Document doc-1 deleted.' });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('usePdfDocumentProcessing', () => {
  it('uploads, extracts, analyzes, and cleans up a temporary PDF', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    // Upload called with a tmp-pdf- prefixed ID.
    expect(mockIngest).toHaveBeenCalledTimes(1);
    const [, thesisId] = mockIngest.mock.calls[0] as [unknown, string];
    expect(thesisId).toMatch(/^tmp-pdf-/);

    // Job polled until completion.
    expect(mockJob).toHaveBeenCalledWith('job-1');

    // Text retrieved from the uploaded document.
    expect(mockText).toHaveBeenCalledWith('doc-1');

    // Analysis function called with combined page text.
    expect(defaultAnalysisFn).toHaveBeenCalledWith('Page one text.\nPage two text.');

    // Temporary document deleted.
    expect(mockDelete).toHaveBeenCalledWith('doc-1');

    // Final state.
    expect(result.current.stage).toBe('complete');
    expect(result.current.result).toEqual({ analysis: 'done' });
    expect(result.current.pdfError).toBe('');
    expect(result.current.isBusy).toBe(false);
  });

  it('passes page text with correct joining order', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(mockText).toHaveBeenCalledWith('doc-1');
    // Pages are joined in page-number order with newline separators.
    expect(defaultAnalysisFn).toHaveBeenCalledWith(
      'Page one text.\nPage two text.'
    );
  });

  it('rejects non-PDF files', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(
        new File(['dummy'], 'document.txt', { type: 'text/plain' })
      );
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(mockIngest).not.toHaveBeenCalled();
    expect(result.current.pdfError).toBe('Please select a PDF file.');
    expect(result.current.stage).toBe('idle');
  });

  it('rejects files exceeding 10 MB', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    const largeFile = new File(['x'.repeat(11 * 1024 * 1024)], 'big.pdf', {
      type: 'application/pdf',
    });

    act(() => {
      result.current.setFile(largeFile);
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(mockIngest).not.toHaveBeenCalled();
    expect(result.current.pdfError).toContain('10 MB');
  });

  it('handles empty PDF with no extractable text', async () => {
    mockText.mockResolvedValue({
      document_id: 'doc-1',
      backend_thesis_id: 'tmp-pdf-abc',
      pages: [],
      total_characters: 0,
      total_pages: 0,
    });

    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(defaultAnalysisFn).not.toHaveBeenCalled();
    expect(result.current.pdfError).toContain('no extractable text');
    expect(result.current.stage).toBe('idle');
    expect(mockDelete).toHaveBeenCalledWith('doc-1');
  });

  it('rejects extracted text exceeding the character limit without truncation', async () => {
    mockText.mockResolvedValue({
      document_id: 'doc-1',
      backend_thesis_id: 'tmp-pdf-abc',
      pages: [
        {
          page_number: 1,
          text: 'x'.repeat(100_001),
          char_offset_start: 0,
          char_offset_end: 100_001,
          is_scanned: false,
        },
      ],
      total_characters: 100_001,
      total_pages: 1,
    });

    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(defaultAnalysisFn).not.toHaveBeenCalled();
    expect(result.current.pdfError).toContain('exceeds');
    expect(result.current.pdfError).toContain('100,000');
  });

  it('cleans up the temporary document after analysis failure', async () => {
    mockJob.mockRejectedValueOnce(new Error('Ingestion failed at stage extraction.'));

    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(result.current.pdfError).toContain('Ingestion failed');
    expect(mockDelete).toHaveBeenCalledWith('doc-1');
  });

  it('does not call the analysis function when extraction fails', async () => {
    mockText.mockRejectedValueOnce(new Error('PDF extraction failed.'));

    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(defaultAnalysisFn).not.toHaveBeenCalled();
    expect(result.current.pdfError).toContain('PDF extraction failed');
  });

  it('continues to completion even when cleanup delete fails', async () => {
    mockDelete.mockRejectedValueOnce(new Error('Delete failed.'));

    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(result.current.stage).toBe('complete');
    expect(result.current.result).toEqual({ analysis: 'done' });
    expect(mockDelete).toHaveBeenCalledWith('doc-1');
  });

  it('resets state when reset is called', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    act(() => {
      result.current.setFile(new File(['dummy'], 'test.pdf', { type: 'application/pdf' }));
    });

    await act(async () => {
      await result.current.processPdf();
    });

    expect(result.current.stage).toBe('complete');

    act(() => {
      result.current.reset();
    });

    expect(result.current.file).toBeNull();
    expect(result.current.stage).toBe('idle');
    expect(result.current.result).toBeNull();
    expect(result.current.pdfError).toBe('');
  });

  it('does not process without a file', async () => {
    const { result } = renderHook(() =>
      usePdfDocumentProcessing({ analysisFn: defaultAnalysisFn })
    );

    await act(async () => {
      await result.current.processPdf();
    });

    expect(mockIngest).not.toHaveBeenCalled();
    expect(result.current.stage).toBe('idle');
  });
});