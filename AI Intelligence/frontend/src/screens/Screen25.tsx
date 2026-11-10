import React, { useState } from 'react';
import { AuthenticatedLayout, Button, useAppRouter } from '../components/shared';
import { userFacingMessage } from '../lib/api';
import { detectGaps } from '../services/aiService';
import { usePdfDocumentProcessing } from '../hooks/usePdfDocumentProcessing';

const formatGapType = (value?: string) =>
  value ? value.replace(/_/g, ' ') : 'candidate gap';

const Screen25GapExplorer = () => {
  const { navigate } = useAppRouter();
  const [input, setInput] = useState('');
  const [gaps, setGaps] = useState<Awaited<ReturnType<typeof detectGaps>>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'text' | 'pdf'>('text');
  const [hasAnalyzed, setHasAnalyzed] = useState(false);

  const {
    file,
    setFile,
    pdfError,
    stage: pdfStage,
    progress: pdfProgress,
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
    setHasAnalyzed(false);
    try {
      setGaps(await detectGaps(input.trim()));
      setHasAnalyzed(true);
    } catch (nextError) {
      setError(userFacingMessage(nextError instanceof Error ? nextError.message : '', 'Gap analysis is unavailable right now. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    setGaps([]);
    setHasAnalyzed(false);
    const nextResult = await processPdfAnalysis();
    if (Array.isArray(nextResult)) {
      setGaps(nextResult);
      setHasAnalyzed(true);
    }
  };

  const isTextBusy = loading || pdfBusy;

  const sourceCount = new Set(gaps.flatMap((gap) => gap.source_thesis_references || [])).size;
  const averageConfidence = gaps.length
    ? Math.round(gaps.reduce((total, gap) => total + (gap.confidence || 0), 0) / gaps.length * 100)
    : null;

  return (
    <AuthenticatedLayout title="Research Gap Explorer">
      <div className="mx-auto max-w-7xl space-y-7 px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-5">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Evidence-based discovery</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Explore candidate research gaps using text from theses you are authorised to access. Findings require indexed evidence and should be reviewed against their sources.
            </p>
          </div>
          <p className="text-xs text-slate-500">Text and PDF analysis</p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(17rem,0.6fr)]">
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Analyze a research area</h2>
                <p className="mt-1 text-sm text-slate-500">Enter a topic or provide a paper to compare with the indexed thesis corpus.</p>
              </div>
            </div>

            <div className="mt-5 inline-flex rounded-md border border-slate-200 bg-slate-50 p-1" role="tablist" aria-label="Analysis input type">
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'text'}
                onClick={() => {
                  setMode('text');
                  setError('');
                  setGaps([]);
                  setHasAnalyzed(false);
                  resetPdf();
                }}
                className={`rounded px-3 py-1.5 text-sm font-medium ${mode === 'text' ? 'bg-white text-emerald-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
              >
                Research topic
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'pdf'}
                onClick={() => {
                  setMode('pdf');
                  setError('');
                  setGaps([]);
                  setHasAnalyzed(false);
                  resetPdf();
                }}
                className={`rounded px-3 py-1.5 text-sm font-medium ${mode === 'pdf' ? 'bg-white text-emerald-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
              >
                Upload PDF
              </button>
            </div>

            {mode === 'text' && (
              <form
                className="mt-5"
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleExplore();
                }}
              >
                <label htmlFor="gap-topic" className="mb-2 block text-sm font-medium text-slate-700">Research topic or question</label>
                <textarea
                  id="gap-topic"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  rows={5}
                  className="w-full resize-y rounded-md border border-slate-300 p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/15"
                  placeholder="Describe the research area you want to explore…"
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-slate-500">Results are based on accessible indexed thesis evidence.</p>
                  <Button type="submit" disabled={isTextBusy || !input.trim()}>
                    {loading ? 'Analyzing evidence…' : 'Find candidate gaps'}
                  </Button>
                </div>
              </form>
            )}

            {mode === 'pdf' && (
              <div className="mt-5 space-y-4">
                <label htmlFor="gap-pdf" className="block text-sm font-medium text-slate-700">PDF document</label>
                <input
                  id="gap-pdf"
                  type="file"
                  accept=".pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="block w-full rounded-md border border-slate-300 bg-white p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-emerald-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-emerald-900"
                />
                {file && <p className="truncate text-xs text-slate-500">Selected: {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</p>}
                <Button disabled={isTextBusy || !file} onClick={handlePdfRun}>
                  {pdfBusy ? 'Analyzing PDF…' : 'Analyze PDF'}
                </Button>
                {pdfError && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{pdfError}</p>}
                {pdfStage !== 'idle' && <p className="text-sm text-slate-600" role="status">{pdfProgress}</p>}
                {scanInfo && scanInfo.scannedPages > 0 && (
                  <p className="rounded-md bg-amber-50 p-3 text-xs text-amber-800">
                    {scanInfo.scannedPages} of {scanInfo.totalPages} pages had no extractable text; analysis covers {scanInfo.extractablePages} pages.
                  </p>
                )}
              </div>
            )}

            {error && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          </section>

          <aside className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <h2 className="text-sm font-semibold text-slate-900">Analysis summary</h2>
            {hasAnalyzed ? (
              <div className="mt-5 space-y-5">
                <div className="grid grid-cols-2 gap-3">
                  <div className="border-l-2 border-emerald-700 pl-3">
                    <p className="text-2xl font-semibold text-slate-900">{gaps.length}</p>
                    <p className="text-xs text-slate-500">candidate gaps</p>
                  </div>
                  <div className="border-l-2 border-slate-300 pl-3">
                    <p className="text-2xl font-semibold text-slate-900">{sourceCount}</p>
                    <p className="text-xs text-slate-500">cited thesis sources</p>
                  </div>
                </div>
                {averageConfidence !== null && <p className="text-sm text-slate-600">Mean confidence across returned findings: <span className="font-medium text-slate-900">{averageConfidence}%</span></p>}
                {gaps.length === 0 && <p className="text-sm leading-6 text-slate-600">No candidate gaps were supported by the evidence returned for this analysis.</p>}
              </div>
            ) : (
              <p className="mt-4 text-sm leading-6 text-slate-500">
                Run an analysis to see findings and source counts. No sample results are shown.
              </p>
            )}
          </aside>
        </div>

        <section aria-labelledby="gap-findings-heading">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 pb-3">
            <div>
              <h2 id="gap-findings-heading" className="text-lg font-semibold text-slate-900">Evidence-backed findings</h2>
              <p className="mt-1 text-sm text-slate-500">Each finding includes its cited thesis evidence where available.</p>
            </div>
            {hasAnalyzed && <span className="text-xs text-slate-500">{gaps.length} returned</span>}
          </div>
          {gaps.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2">
              {gaps.map((gap, index) => (
                <article key={`${gap.gap_type}-${index}`} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-semibold capitalize text-slate-900">{formatGapType(gap.gap_type)}</h3>
                    <span className="shrink-0 text-xs text-slate-500">{Math.round((gap.confidence ?? 0) * 100)}% confidence</span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    {gap.description || gap.explanation || 'Review the cited evidence before treating this as a confirmed gap.'}
                  </p>
                  {gap.suggested_research_direction && <p className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700"><span className="font-medium">Possible direction:</span> {gap.suggested_research_direction}</p>}
                  <p className="mt-3 text-xs text-slate-500">
                    {gap.source_origin === 'author_stated' ? 'Stated by an author' : 'Inferred from retrieved evidence'} · {gap.source_thesis_references?.length ?? 0} source(s)
                  </p>
                  {gap.chunk_citations && gap.chunk_citations.length > 0 && (
                    <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
                      <p className="text-xs font-semibold text-slate-600">Source passages</p>
                      {gap.chunk_citations.slice(0, 3).map((citation, citeIndex) => (
                        <div key={citeIndex} className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
                          <p className="italic">“{citation.text_snippet}”</p>
                          <p className="mt-2 text-slate-500">Thesis {citation.backend_thesis_id}{citation.page_number !== null ? ` · page ${citation.page_number}` : ''}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-slate-500">
              {hasAnalyzed ? 'No candidate gaps were returned for this evidence.' : 'Findings will appear here after you run an analysis.'}
            </p>
          )}
        </section>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen25GapExplorer;