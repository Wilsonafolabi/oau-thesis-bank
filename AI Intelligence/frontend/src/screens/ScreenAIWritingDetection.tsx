import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, Badge, useAppRouter } from '../components/shared';
import { ApiError } from '../lib/api';
import {
  detectAIWriting,
  type AIWritingBand,
  type AIWritingDetectResponse,
} from '../services/aiService';
import { usePdfDocumentProcessing, type PdfStage } from '../hooks/usePdfDocumentProcessing';

const BAND_LABEL: Record<AIWritingBand, string> = {
  likely_ai: 'Likely AI-generated',
  uncertain: 'Uncertain',
  likely_human: 'Likely human-written',
};

const BAND_STYLE: Record<AIWritingBand, string> = {
  likely_ai: 'text-amber-700 bg-amber-50',
  uncertain: 'text-slate-700 bg-slate-50',
  likely_human: 'text-emerald-700 bg-emerald-50',
};

const ScreenAIWritingDetection = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState<AIWritingDetectResponse | null>(null);
  const [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'text' | 'pdf'>('text');

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  const {
    file,
    setFile,
    pdfError,
    stage: pdfStage,
    progress: pdfProgress,
    result: pdfResult,
    isBusy: pdfBusy,
    processPdf: processPdfAnalysis,
    reset: resetPdf,
    scanInfo,
  } = usePdfDocumentProcessing({
    analysisFn: async (txt) => {
      return await detectAIWriting(txt);
    },
    maxChars: 50_000,
  });

  const handleDetect = async () => {
    setLoading(true);
    setError('');
    setUnavailable('');
    setResult(null);

    try {
      if (!text.trim()) {
        setError('Please enter some text to analyse.');
        return;
      }
      setResult(await detectAIWriting(text));
    } catch (err) {
      // 503 means the detector itself could not run. No score is shown.
      if (err instanceof ApiError && err.status === 503) {
        setUnavailable(err.detail || 'The AI-writing detector is not available.');
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('AI writing detection failed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    setUnavailable('');
    setResult(null);
    await processPdfAnalysis();
    if (pdfResult && typeof pdfResult === 'object' && 'status' in pdfResult) {
      setResult(pdfResult as AIWritingDetectResponse);
    }
  };

  const isTextBusy = loading || pdfBusy;

  return (
    <AuthenticatedLayout title="AI Writing Detection">
      <div className="mx-auto max-w-4xl space-y-6">
        <Card className="p-6 bg-amber-50 border border-amber-200">
          <h3 className="text-sm font-bold text-amber-900 mb-2">Read this first</h3>
          <p className="text-sm text-amber-800 leading-relaxed">
            This detector returns a <strong>probabilistic signal about a text</strong>, not
            evidence about its author. It produces false positives on short or technical
            human writing and has not been validated on OAU theses. It must never be used as
            the sole basis for a disciplinary decision.
          </p>
        </Card>

        <Card className="p-6">
          <h2 className="text-xl font-bold text-slate-900 mb-2">Check a passage</h2>
          <p className="text-sm text-slate-600 mb-6">
            Paste text of at least 60 words, or upload a PDF. The detector supports English
            only; scanned PDFs without extractable text cannot be analysed.
          </p>

          {/* Mode selector */}
          <div className="mt-4 flex gap-2 border-b border-slate-200 pb-2">
            <Button
              variant={mode === 'text' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setMode('text');
                setError('');
                setUnavailable('');
                setResult(null);
                resetPdf();
              }}
            >
              Paste text
            </Button>
            <Button
              variant={mode === 'pdf' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setMode('pdf');
                setError('');
                setUnavailable('');
                setResult(null);
                resetPdf();
              }}
            >
              Upload PDF
            </Button>
          </div>

          {mode === 'text' && (
            <div className="mt-6">
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={8}
                aria-label="Text to analyse"
                className="w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Paste the text you want to analyse…"
              />

              <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                <span>{wordCount} words</span>
                <span>Minimum 60 words · maximum 50,000 characters</span>
              </div>

              <Button
                className="mt-4"
                disabled={isTextBusy || !text.trim()}
                onClick={handleDetect}
              >
                {isTextBusy ? 'Analysing…' : 'Run detection'}
              </Button>

              {error && (
                <p role="alert" className="mt-3 rounded-md bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </p>
              )}
            </div>
          )}

          {mode === 'pdf' && (
            <div className="mt-6 space-y-4">
              <label
                htmlFor="ai-writing-pdf"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                PDF document
              </label>
              <div className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm flex items-center gap-3">
                <input
                  id="ai-writing-pdf"
                  type="file"
                  accept=".pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="w-full text-sm"
                />
                {file && (
                  <div className="flex-1 truncate">
                    <p className="text-sm text-slate-900">{file.name}</p>
                    <p className="text-xs text-slate-500">{file.size} bytes</p>
                  </div>
                )}
                {file && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      setFile(null);
                      resetPdf();
                    }}
                    disabled={pdfBusy}
                  >
                    Remove
                  </Button>
                )}
              </div>
              {pdfError && (
                <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                  {pdfError}
                </p>
              )}
              {pdfStage !== 'idle' && (
                <Card className="p-4 bg-slate-50 border border-slate-200">
                  <p className="text-sm text-slate-600">{pdfProgress}</p>
                  {pdfStage === 'complete' && (
                    <>
                      <p className="mt-2 text-sm text-emerald-700">
                        PDF analyzed. Results below.
                      </p>
                      {scanInfo && scanInfo.scannedPages > 0 && (
                        <p className="mt-1 text-xs text-amber-700 bg-amber-50/50 p-2 rounded">
                          {scanInfo.scannedPages} of {scanInfo.totalPages} page(s)
                          could not be extracted (scanned or image-based). Detection
                          covers only the {scanInfo.extractablePages} extractable
                          page(s).
                        </p>
                      )}
                    </>
                  )}
                </Card>
              )}
            </div>
          )}
        </Card>

        {unavailable && (
          <Card className="p-6 border border-slate-300 bg-slate-50">
            <h3 className="text-sm font-bold text-slate-900 mb-2">
              Detection unavailable
            </h3>
            <p className="text-sm text-slate-700 leading-relaxed">{unavailable}</p>
            <p className="mt-2 text-xs text-slate-500">
              No probability is shown because no detection was performed.
            </p>
          </Card>
        )}

        {result && result.status !== 'ok' && (
          <Card className="p-6 border border-slate-300 bg-slate-50">
            <h3 className="text-sm font-bold text-slate-900 mb-2">
              {result.status === 'insufficient_text'
                ? 'Not enough text to analyse'
                : result.status === 'unsupported_language'
                  ? 'Unsupported language'
                  : 'Detection unavailable'}
            </h3>
            <ul className="text-sm text-slate-700 list-disc list-inside space-y-1">
              {result.limitations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
            {result.blocker && (
              <p className="mt-2 text-xs text-slate-500">{result.blocker}</p>
            )}
            <p className="mt-2 text-xs text-slate-500">
              No probability is shown because no detection was performed.
            </p>
          </Card>
        )}

        {result && result.status === 'ok' && result.ai_probability !== null && (
          <div className="space-y-6">
            <Card className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-500">AI-generated signal</p>
                  <p
                    className={`text-3xl font-bold ${
                      result.assessment ? BAND_STYLE[result.assessment] : ''
                    }`}
                  >
                    {(result.ai_probability * 100).toFixed(1)}%
                  </p>
                  {result.assessment && (
                    <p className="mt-1 text-xs font-medium text-slate-600">
                      {BAND_LABEL[result.assessment]}
                    </p>
                  )}
                </div>
                <div className="text-right text-xs text-slate-500">
                  {result.calibration && <p>Calibration: {result.calibration}</p>}
                  <p>Segments analysed: {result.segments.length}</p>
                  {result.confidence !== null && (
                    <p>
                      Segment agreement: {(result.confidence * 100).toFixed(0)}% (agreement
                      across segments, not model certainty)
                    </p>
                  )}
                </div>
              </div>
              {result.model_id && (
                <p className="mt-3 text-xs text-slate-400">
                  Detector: {result.model_id}
                  {result.model_version ? ` @ ${result.model_version.slice(0, 12)}` : ''}
                </p>
              )}
            </Card>

            {result.segments.length > 0 && (
              <Card className="p-6">
                <h3 className="text-lg font-bold text-slate-900 mb-4">
                  Per-segment results
                </h3>
                <div className="space-y-3">
                  {result.segments.map((segment, index) => (
                    <div
                      key={index}
                      className="rounded-md border border-slate-100 p-3 last:border-b-0"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-500">
                          Segment {index + 1} · characters {segment.start_char}–
                          {segment.end_char}
                        </span>
                        <Badge variant="blue" className="text-xs">
                          {(segment.ai_probability * 100).toFixed(1)}% ·
                          {segment.band}
                        </Badge>
                      </div>
                      <p className="text-sm italic text-slate-600">
                        “{segment.text}”
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {result.limitations.length > 0 && (
              <Card className="p-6">
                <h3 className="text-sm font-bold text-slate-900 mb-2">Limitations</h3>
                <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
                  {result.limitations.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </Card>
            )}

            <Card className="p-6 bg-amber-50 border border-amber-200">
              <p className="text-sm text-amber-800 leading-relaxed">
                {result.disclaimer}
              </p>
            </Card>

            <div className="flex justify-end">
              <Button onClick={() => setResult(null)}>New analysis</Button>
            </div>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default ScreenAIWritingDetection;