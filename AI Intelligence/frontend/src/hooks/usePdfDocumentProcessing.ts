/**
 * Shared PDF document processing hook for research intelligence tools.
 *
 * Encapsulates the complete temporary-PDF workflow so it is not duplicated
 * across screens:
 *
 * 1. File selection and validation (.pdf only, ≤10 MB)
 * 2. Upload via the existing ingestion API with a unique temporary ID
 * 3. Background job polling until completion or failure
 * 4. Extracted page-text retrieval with page metadata preservation
 * 5. Extracted-text size validation (≤100,000 characters; no truncation)
 * 6. Passing extracted content to the tool's own analysis API
 * 7. Temporary document cleanup after success or failure
 *
 * Each screen supplies its own analysis function; this hook owns the PDF
 * lifecycle only. No browser-side PDF extraction is used.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ingestThesisPdf,
  getAIDocumentJob,
  getDocumentText,
  deleteAIDocument,
  type DocumentPageText,
} from '../services/aiService';

const MAX_PDF_SIZE_MB = 10;
const MAX_TEXT_CHARS_DEFAULT = 100_000;
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 60; // up to ~2 minutes

export type PdfStage = 'idle' | 'uploading' | 'extracting' | 'analyzing' | 'complete';

interface UsePdfDocumentProcessingConfig {
  /** The tool's own analysis function, called with the extracted text. */
  analysisFn: (text: string) => Promise<unknown>;
  /** Maximum allowed extracted text characters (default 100,000). */
  maxChars?: number;
}

interface UsePdfDocumentProcessingReturn {
  file: File | null;
  setFile: (file: File | null) => void;
  pdfError: string;
  stage: PdfStage;
  progress: string;
  result: unknown | null;
  isBusy: boolean;
  cleanupError: string | null;
  cleanupLog: Array<{ documentId: string; success: boolean; error?: string }>;
  scanInfo: {
    totalPages: number;
    extractablePages: number;
    scannedPages: number;
  } | null;
  processPdf: () => Promise<void>;
  cleanup: () => Promise<void>;
  reset: () => void;
}

export const usePdfDocumentProcessing = (
  config: UsePdfDocumentProcessingConfig
): UsePdfDocumentProcessingReturn => {
  const { analysisFn, maxChars = MAX_TEXT_CHARS_DEFAULT } = config;
  const analysisFnRef = useRef(analysisFn);
  analysisFnRef.current = analysisFn;

  const [file, setFile] = useState<File | null>(null);
  const [pdfError, setPdfError] = useState('');
  const [stage, setStage] = useState<PdfStage>('idle');
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState<unknown | null>(null);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [cleanupLog, setCleanupLog] = useState<Array<{
    documentId: string;
    success: boolean;
    error?: string;
  }>>([]);
  const [scanInfo, setScanInfo] = useState<{
    totalPages: number;
    extractablePages: number;
    scannedPages: number;
  } | null>(null);

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const documentIdRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, []);

  const cleanup = useCallback(async (): Promise<void> => {
    const documentId = documentIdRef.current;
    if (!documentId) return;

    documentIdRef.current = null;

    try {
      await deleteAIDocument(documentId);
      setCleanupLog((prev) => [
        ...prev,
        { documentId, success: true },
      ]);
      setCleanupError(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Cleanup failed.';
      // Log with document ID for observability; do not overwrite a successful
      // analysis result, and do not silently swallow the failure.
      setCleanupLog((prev) => [
        ...prev,
        { documentId, success: false, error: errorMessage },
      ]);
      setCleanupError(errorMessage);
      console.error(
        `[usePdfDocumentProcessing] Temporary document cleanup failed: documentId=${documentId} error=${errorMessage}`
      );
    }
  }, []);

  const reset = useCallback(() => {
    setFile(null);
    setPdfError('');
    setStage('idle');
    setProgress('');
    setResult(null);
    setCleanupError(null);
    setCleanupLog([]);
    setScanInfo(null);
    documentIdRef.current = null;
  }, []);

  const validatePdfFile = useCallback(
    (f: File): string | null => {
      if (!f.name.toLowerCase().endsWith('.pdf')) {
        return 'Please select a PDF file.';
      }
      if (f.size > MAX_PDF_SIZE_MB * 1024 * 1024) {
        return `PDF exceeds the ${MAX_PDF_SIZE_MB} MB size limit.`;
      }
      return null;
    },
    []
  );

  const pollJob = useCallback(
    async (jobId: string): Promise<void> => {
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await new Promise((resolve) => {
          pollRef.current = setTimeout(resolve, POLL_INTERVAL_MS);
        });

        const job = await getAIDocumentJob(jobId);
        if (job.status === 'completed') {
          return;
        }
        if (job.status === 'failed') {
          throw new Error(
            job.error_message || `Ingestion failed at stage ${job.stage}.`
          );
        }
        setProgress(
          job.stage === 'extraction'
            ? 'Extracting text from PDF…'
            : job.stage === 'chunking'
              ? 'Chunking document…'
              : job.stage === 'embedding'
                ? 'Generating embeddings…'
                : 'Processing document…'
        );
      }
      throw new Error('Document processing timed out. Please try again.');
    },
    []
  );

  const processPdf = useCallback(async (): Promise<void> => {
    if (!file) return;

    const validationError = validatePdfFile(file);
    if (validationError) {
      setPdfError(validationError);
      return;
    }

    setPdfError('');
    setResult(null);
    documentIdRef.current = null;

    try {
      // Step 1: Upload with a unique temporary thesis ID.
      setStage('uploading');
      setProgress('Uploading PDF…');
      const tempThesisId = `tmp-pdf-${crypto.randomUUID()}`;
      const upload = await ingestThesisPdf(file, tempThesisId, {
        title: file.name,
      });
      documentIdRef.current = upload.document_id;
      setProgress('Upload complete. Processing…');

      // Step 2: Poll the ingestion job until completion or failure.
      setStage('extracting');
      await pollJob(upload.job_id);

      // Step 3: Retrieve the extracted text with page mappings.
      if (!documentIdRef.current) {
        throw new Error('Document identifier was not returned.');
      }
      setProgress('Retrieving extracted text…');
      const textResponse = await getDocumentText(documentIdRef.current);

      const totalPages = textResponse.total_pages;
      const extractablePages = textResponse.pages.filter(
        (page) => page.text && page.text.trim().length > 0
      ).length;
      const scannedPages = totalPages - extractablePages;
      setScanInfo({
        totalPages,
        extractablePages,
        scannedPages,
      });

      const fullText = textResponse.pages
        .map((page) => page.text || '')
        .join('\n')
        .trim();

      if (!fullText) {
        throw new Error(
          'The PDF contains no extractable text. It may be scanned or image-based; OCR is not available.'
        );
      }

      // Step 4: Enforce the character limit before analysis — no truncation.
      if (fullText.length > maxChars) {
        throw new Error(
          `Extracted text is ${fullText.length.toLocaleString()} characters, which exceeds the ${maxChars.toLocaleString()} character limit for analysis. Please upload a smaller PDF or paste a shorter excerpt instead.`
        );
      }

      // Step 5: Run the tool's own analysis function.
      setStage('analyzing');
      setProgress('Analysing document…');
      const analysisResult = await analysisFnRef.current(fullText);
      setResult(analysisResult);

      setStage('complete');
      setProgress('Analysis complete.');
    } catch (err) {
      if (err instanceof Error) {
        setPdfError(err.message);
      } else {
        setPdfError('PDF processing failed.');
      }
      setStage('idle');
    } finally {
      await cleanup();
      setProgress('');
    }
  }, [file, validatePdfFile, pollJob, cleanup, maxChars]);

  const isBusy = stage !== 'idle' && stage !== 'complete';

  return {
    file,
    setFile,
    pdfError,
    stage,
    progress,
    result,
    isBusy,
    cleanupError,
    cleanupLog,
    scanInfo,
    processPdf,
    cleanup,
    reset,
  };
};

export type { DocumentPageText };