import React, { useState } from 'react';
import { AuthenticatedLayout, Button, useAppRouter } from '../components/shared';
import { ArrowRight, FileText, Lightbulb, Upload } from 'lucide-react';
import { ApiError, apiErrorMessage } from '../lib/api';
import { checkSimilarityText } from '../services/aiService';
import { usePdfDocumentProcessing } from '../hooks/usePdfDocumentProcessing';
import { SIMILARITY_REPORT_KEY } from './Screen23';

const Screen22IdeaChecker = () => {
  const { navigate } = useAppRouter();
  const [ideaText, setIdeaText] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'text' | 'pdf'>('text');

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
    analysisFn: async (text) => {
      const report = await checkSimilarityText(text.trim());
      sessionStorage.setItem(SIMILARITY_REPORT_KEY, JSON.stringify(report));
      navigate('idea-similarity');
      return report;
    },
    maxChars: 100_000,
  });

  const handleCheckText = async () => {
    if (!ideaText.trim()) return;
    setLoading(true);
    setError('');
    try {
      const report = await checkSimilarityText(ideaText.trim());
      sessionStorage.setItem(SIMILARITY_REPORT_KEY, JSON.stringify(report));
      navigate('idea-similarity');
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('You do not have access to one or more compared documents.');
      } else {
        setError(apiErrorMessage(err, 'Similarity comparison is unavailable right now. Please try again.'));
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    await processPdfAnalysis();
  };

  const isTextBusy = loading || pdfBusy;

  return (
    <AuthenticatedLayout title="Research Idea Checker">
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:py-12">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-800">
            <Lightbulb className="h-6 w-6" aria-hidden="true" />
          </div>
          <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-emerald-800">Novelty review</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-900">Has your idea been explored?</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
            Compare a proposed study with thesis text in the OAU repository. Only documents you are authorised to read are included; similarity is a review signal, not proof of novelty or plagiarism.
          </p>
        </div>

        <section className="mx-auto mt-8 max-w-3xl rounded-lg border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
          <div className="mb-5 inline-flex rounded-md border border-slate-200 bg-slate-50 p-1" role="tablist" aria-label="Idea input type">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'text'}
              onClick={() => {
                setMode('text');
                setError('');
                resetPdf();
              }}
              className={`rounded px-3 py-1.5 text-sm font-medium ${mode === 'text' ? 'bg-white text-emerald-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
            >
              <FileText className="mr-2 inline h-4 w-4" aria-hidden="true" />Paste text
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'pdf'}
              onClick={() => {
                setMode('pdf');
                setError('');
                resetPdf();
              }}
              className={`rounded px-3 py-1.5 text-sm font-medium ${mode === 'pdf' ? 'bg-white text-emerald-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
            >
              <Upload className="mr-2 inline h-4 w-4" aria-hidden="true" />Upload PDF
            </button>
          </div>

          {mode === 'text' && (
            <form onSubmit={(event) => { event.preventDefault(); void handleCheckText(); }}>
              <label htmlFor="similarity-text" className="mb-2 block text-sm font-medium text-slate-700">Proposed research</label>
              <textarea
                id="similarity-text"
                value={ideaText}
                onChange={(event) => setIdeaText(event.target.value)}
                rows={8}
                className="w-full resize-y rounded-md border border-slate-300 p-4 text-sm leading-6 text-slate-900 placeholder:text-slate-400 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/15"
                placeholder="Describe your proposed research idea…"
              />
              <p className="mt-3 text-xs leading-5 text-slate-500">
                The checker looks for exact, near-exact, partial wording overlap, and semantic similarity when available.
              </p>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-slate-500">Compared with accessible, indexed repository text.</p>
                <Button type="submit" disabled={isTextBusy || !ideaText.trim()}>
                  {loading ? 'Checking repository…' : <>Analyze my idea <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" /></>}
                </Button>
              </div>
            </form>
          )}

          {mode === 'pdf' && (
            <div className="space-y-4">
              <label htmlFor="similarity-pdf" className="block text-sm font-medium text-slate-700">Research PDF</label>
              <input
                id="similarity-pdf"
                type="file"
                accept=".pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="block w-full rounded-md border border-slate-300 bg-white p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-emerald-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-emerald-900"
              />
              {file && <p className="truncate text-xs text-slate-500">Selected: {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</p>}
              <Button disabled={isTextBusy || !file} onClick={handlePdfRun}>
                {pdfBusy ? 'Checking PDF…' : <>Analyze PDF <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" /></>}
              </Button>
              {pdfError && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{pdfError}</p>}
              {error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
              {pdfStage !== 'idle' && <p role="status" className="text-sm text-slate-600">{pdfProgress}</p>}
              {scanInfo && scanInfo.scannedPages > 0 && <p className="rounded-md bg-amber-50 p-3 text-xs text-amber-800">{scanInfo.scannedPages} of {scanInfo.totalPages} pages had no extractable text; results cover {scanInfo.extractablePages} pages.</p>}
            </div>
          )}
        </section>

        <p className="mx-auto mt-5 max-w-3xl text-center text-xs leading-5 text-slate-500">
          Similarity is an indicator for review, not a plagiarism finding. Temporary PDF uploads are removed after the check and are not added to the repository.
        </p>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;