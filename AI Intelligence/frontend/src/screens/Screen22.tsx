import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { ApiError } from '../lib/api';
import { checkSimilarityText } from '../services/aiService';
import { usePdfDocumentProcessing, type PdfStage } from '../hooks/usePdfDocumentProcessing';
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
    result: pdfResult,
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
      } else if (err instanceof ApiError && err.status === 503) {
        setError(err.detail || 'Semantic comparison is unavailable right now.');
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Similarity check failed.');
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
      <div className="mx-auto max-w-3xl space-y-6">
        <Card className="p-6">
          <h2 className="text-2xl font-bold text-slate-900">Check research similarity</h2>
          <p className="mt-2 text-sm text-slate-600">
            Compare your research idea against thesis text in the OAU repository.
            Only documents you are authorised to read are compared.
          </p>

          {/* Mode selector */}
          <div className="mt-6 flex gap-2 border-b border-slate-200 pb-2">
            <Button
              variant={mode === 'text' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setMode('text');
                setError('');
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
                resetPdf();
              }}
            >
              Upload PDF
            </Button>
          </div>

          {/* Text input mode */}
          {mode === 'text' && (
            <div className="mt-6">
              <label
                htmlFor="similarity-text"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                Research idea text
              </label>
              <textarea
                id="similarity-text"
                value={ideaText}
                onChange={(event) => setIdeaText(event.target.value)}
                rows={6}
                className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Describe your proposed research idea…"
              />
              <p className="mt-1 text-xs text-slate-500">
                Compared as 200-word passages: exact, near-exact and partial wording overlap,
                plus semantic similarity where the vector index is available.
              </p>
              <Button
                className="mt-4"
                disabled={isTextBusy || !ideaText.trim()}
                onClick={handleCheckText}
              >
                {isTextBusy ? 'Checking similarity…' : 'Check similarity'}
              </Button>
              {error && (
                <p role="alert" className="mt-3 rounded-md bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </p>
              )}
            </div>
          )}

          {/* PDF upload mode */}
          {mode === 'pdf' && (
            <div className="mt-6 space-y-4">
              <label
                htmlFor="similarity-pdf"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                PDF document
              </label>
              <div className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm flex items-center gap-3">
                <input
                  id="similarity-pdf"
                  type="file"
                  accept=".pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="w-full text-sm"
                />
                {file && (
                  <div className="flex-1 truncate">
                    <p className="text-sm text-slate-900">{file.name}</p>
                    <p className="text-xs text-slate-500">
                      {file.size} bytes · max 10 MB
                    </p>
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
                        PDF processed. Opening similarity results…
                      </p>
                      {scanInfo && scanInfo.scannedPages > 0 && (
                        <p className="mt-1 text-xs text-amber-700 bg-amber-50/50 p-2 rounded">
                          {scanInfo.scannedPages} of {scanInfo.totalPages} page(s)
                          could not be extracted (scanned or image-based). Similarity
                          results cover only the {scanInfo.extractablePages} extractable
                          page(s).
                        </p>
                      )}
                    </>
                  )}
                </Card>
              )}
            </div>
          )}

          {mode === 'pdf' && (
            <div className="mt-6 space-y-2">
              <Button
                className="mt-4"
                disabled={isTextBusy || !file}
                onClick={handlePdfRun}
              >
                {pdfStage === 'complete'
                  ? 'Opening results…'
                  : pdfStage === 'idle'
                    ? 'Upload and check PDF'
                    : `Processing… ${pdfProgress}`}
              </Button>
              {error && (
                <p role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
                  {error}
                </p>
              )}
            </div>
          )}
        </Card>

        <Card className="p-6 bg-slate-50 border border-slate-200">
          <p className="text-sm text-slate-600">
            Similarity is an indicator for review, not a plagiarism finding. Use the
            plagiarism assessment screen for attribution-aware analysis. Temporary
            PDF uploads are deleted automatically after the check; no permanent
            repository record is created.
          </p>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;