import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, Badge, useAppRouter } from '../components/shared';
import { ApiError } from '../lib/api';
import {
  assessPlagiarism,
  type PlagiarismResponse,
  type PlagiarismStatus,
} from '../services/aiService';
import { usePdfDocumentProcessing, type PdfStage } from '../hooks/usePdfDocumentProcessing';

const STATUS_LABEL: Record<PlagiarismStatus, string> = {
  attribution_present: 'Attribution detected',
  review_required: 'Manual review recommended',
  no_significant_overlap: 'No significant overlap detected',
};

const STATUS_STYLE: Record<PlagiarismStatus, string> = {
  attribution_present: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  review_required: 'bg-amber-50 text-amber-800 border-amber-200',
  no_significant_overlap: 'bg-slate-50 text-slate-700 border-slate-200',
};

const ScreenPlagiarismAssess = () => {
  const [text, setText] = useState('');
  const [result, setResult] = useState<PlagiarismResponse | null>(null);
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
    analysisFn: async (txt) => {
      return await assessPlagiarism({ text: txt.trim() });
    },
    maxChars: 100_000,
  });

  const handleAssess = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(await assessPlagiarism({ text: text.trim() }));
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('The assessment could not be completed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    setResult(null);
    const nextResult = await processPdfAnalysis();
    if (nextResult && typeof nextResult === 'object' && 'status' in nextResult) {
      setResult(nextResult as PlagiarismResponse);
    }
  };

  const isTextBusy = loading || pdfBusy;

  return (
    <AuthenticatedLayout title="Plagiarism Review">
      <div className="mx-auto max-w-4xl space-y-6">
        <Card className="p-6 bg-slate-50 border border-slate-200">
          <h3 className="text-sm font-bold text-slate-900 mb-2">What this does</h3>
          <p className="text-sm text-slate-700 leading-relaxed">
            This checks whether overlapping text is <strong>quoted or cited</strong>. It is
            not a plagiarism verdict and never names anyone as having plagiarised. A
            quotation with attribution is not an accusation.
          </p>
        </Card>

        <Card className="p-6">
          <h2 className="text-xl font-bold text-slate-900 mb-2">Assess a passage</h2>
          <p className="text-sm text-slate-600 mb-4">
            Paste the text you want reviewed, or upload a PDF. Only repository documents you
            are authorised to read are compared.
          </p>

          {/* Mode selector */}
          <div className="mt-4 flex gap-2 border-b border-slate-200 pb-2">
            <Button
              variant={mode === 'text' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => {
                setMode('text');
                setError('');
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
                aria-label="Text to assess"
                className="w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Paste the passage to assess…"
              />
              <Button
                className="mt-4"
                disabled={isTextBusy || !text.trim()}
                onClick={handleAssess}
              >
                {isTextBusy ? 'Assessing…' : 'Assess attribution'}
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
                htmlFor="plagiarism-pdf"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                PDF document
              </label>
              <div className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm flex items-center gap-3">
                <input
                  id="plagiarism-pdf"
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
              <Button
                disabled={isTextBusy || !file}
                onClick={handlePdfRun}
              >
                {pdfBusy ? 'Assessing PDF…' : 'Assess PDF'}
              </Button>
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
                        PDF assessed. Results below.
                      </p>
                      {scanInfo && scanInfo.scannedPages > 0 && (
                        <p className="mt-1 text-xs text-amber-700 bg-amber-50/50 p-2 rounded">
                          {scanInfo.scannedPages} of {scanInfo.totalPages} page(s)
                          could not be extracted (scanned or image-based). Assessment
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

        {result && (
          <div className="space-y-6">
            <Card className={`p-6 border ${STATUS_STYLE[result.status]}`}>
              <h3 className="text-lg font-bold">{STATUS_LABEL[result.status]}</h3>
              <p className="mt-1 text-sm">
                {result.matched_source_count} matching source
                {result.matched_source_count === 1 ? '' : 's'} found.
              </p>
            </Card>

            {result.passages.length > 0 && (
              <Card className="p-6">
                <h3 className="text-lg font-bold text-slate-900 mb-4">Passages</h3>
                <div className="space-y-4">
                  {result.passages.map((passage, index) => (
                    <div key={index} className="rounded-md border border-slate-100 p-4">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge
                          variant={
                            passage.assessment === 'review_required' ? 'gray' : 'blue'
                          }
                          className="text-xs"
                        >
                          {STATUS_LABEL[passage.assessment]}
                        </Badge>
                        {passage.quoted && (
                          <span className="text-xs text-slate-500">
                            Quotation marks found
                          </span>
                        )}
                        {passage.cited && (
                          <span className="text-xs text-slate-500">
                            Citation found
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-700">{passage.reason}</p>
                      <p className="mt-2 text-sm italic text-slate-600">
                        “{passage.submitted_excerpt}”
                      </p>
                      {passage.matches.map((match, matchIndex) => (
                        <div
                          key={`${match.chunk_id}-${matchIndex}`}
                          className="mt-3 rounded bg-slate-50 p-3 text-xs text-slate-600"
                        >
                          <p className="font-medium text-slate-700">
                            {match.title || `Thesis ${match.backend_thesis_id}`}
                            {match.page_number !== null ? ` · page ${match.page_number}` : ''}
                          </p>
                          <p className="mt-1 italic">{match.source_excerpt}</p>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {result.limitations.length > 0 && (
              <Card className="p-6">
                <h3 className="text-sm font-bold text-slate-900 mb-2">Limitations</h3>
                <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
                  {result.limitations.map((limitation, index) => (
                    <li key={index}>{limitation}</li>
                  ))}
                </ul>
              </Card>
            )}

            <Card className="p-6 bg-amber-50 border border-amber-200">
              <p className="text-sm text-amber-800 leading-relaxed">
                {result.disclaimer}
              </p>
            </Card>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default ScreenPlagiarismAssess;