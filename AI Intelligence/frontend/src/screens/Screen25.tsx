import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { detectGaps } from '../services/aiService';
import { usePdfDocumentProcessing, type PdfStage } from '../hooks/usePdfDocumentProcessing';

const formatGapType = (value?: string) =>
  value ? value.replace(/_/g, ' ') : 'candidate gap';

const Screen25GapExplorer = () => {
  const { navigate } = useAppRouter();
  const [input, setInput] = useState('');
  const [gaps, setGaps] = useState<Awaited<ReturnType<typeof detectGaps>>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'text' | 'pdf'>('text');

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
      return await detectGaps(txt.trim());
    },
    maxChars: 100_000,
  });

  const handleExplore = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError('');
    try {
      setGaps(await detectGaps(input.trim()));
    } catch (nextError) {
      setError(
        nextError instanceof Error ? nextError.message : 'Gap detection failed.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    setGaps([]);
    await processPdfAnalysis();
    if (Array.isArray(pdfResult)) {
      setGaps(pdfResult);
    }
  };

  const isTextBusy = loading || pdfBusy;

  return (
    <AuthenticatedLayout title="Research Gap Explorer">
      <div className="mx-auto max-w-4xl space-y-6">
        <Card className="p-6">
          <h2 className="text-2xl font-bold text-slate-900">Explore Research Gaps</h2>
          <p className="mt-2 text-sm text-slate-600">
            Enter a research topic, or upload a PDF. The system will extract the document
            text and identify candidate underrepresented areas in the repository.
          </p>

          {/* Mode selector */}
          <div className="mt-6 flex gap-2 border-b border-slate-200 pb-2">
            <Button
              variant={mode === 'text' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setMode('text');
                setError('');
                setGaps([]);
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
                setGaps([]);
                resetPdf();
              }}
            >
              Upload PDF
            </Button>
          </div>

          {mode === 'text' && (
            <div className="mt-6">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={4}
                className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Enter a research topic…"
              />
              <Button
                className="mt-4"
                disabled={isTextBusy || !input.trim()}
                onClick={() => void handleExplore()}
              >
                {isTextBusy ? 'Analyzing corpus…' : 'Find Candidate Gaps'}
              </Button>
              {error && (
                <p className="mt-3 rounded-md bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </p>
              )}
            </div>
          )}

          {mode === 'pdf' && (
            <div className="mt-6 space-y-4">
              <label
                htmlFor="gap-pdf"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                PDF document
              </label>
              <div className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm flex items-center gap-3">
                <input
                  id="gap-pdf"
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
                          could not be extracted (scanned or image-based). Gap
                          analysis covers only the {scanInfo.extractablePages}
                          extractable page(s).
                        </p>
                      )}
                    </>
                  )}
                </Card>
              )}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {gaps.map((gap, index) => (
            <Card
              key={`${gap.gap_type}-${index}`}
              className="cursor-pointer p-5 hover:shadow-md"
              onClick={() => navigate('gap-detail', { topic: gap.gap_type })}
            >
              <div className="flex items-center justify-between gap-4">
                <h3 className="font-bold capitalize text-slate-900">
                  {formatGapType(gap.gap_type)}
                </h3>
                <span className="text-sm text-slate-500">
                  {gap.source_thesis_references?.length ?? 0} sources
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {gap.description || gap.explanation || 'Candidate underrepresented area; review the evidence before treating it as a confirmed gap.'}
              </p>
              <p className="mt-2 text-xs text-slate-400">
                Origin: {gap.source_origin || 'system_inferred'} · Confidence: {Math.round((gap.confidence ?? 0) * 100)}%
              </p>
              {gap.chunk_citations && gap.chunk_citations.length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="text-[10px] font-semibold text-slate-500 uppercase mb-1">
                    Source references
                  </p>
                  {gap.chunk_citations.slice(0, 3).map((citation, citeIndex) => (
                    <div
                      key={citeIndex}
                      className="rounded-md border border-slate-100 p-2 text-xs text-slate-600"
                    >
                      <p className="mb-1 italic">“{citation.text_snippet}”</p>
                      <p className="text-[10px] text-slate-500">
                        Thesis {citation.backend_thesis_id}
                        {citation.page_number !== null ? ` · page ${citation.page_number}` : ''}
                      </p>
                    </div>
                  ))}
                  {gap.chunk_citations.length > 3 && (
                    <p className="text-[10px] text-slate-400">
                      +{gap.chunk_citations.length - 3} more source reference(s)
                    </p>
                  )}
                </div>
              )}
            </Card>
          ))}
          {gaps.length === 0 && !isTextBusy && !error && (
            <p className="text-sm text-slate-500 text-center">
              No candidate gaps found. Try a different topic or upload a PDF.
            </p>
          )}
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen25GapExplorer;