import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { userFacingMessage } from '../lib/api';
import {
  extendIdea,
  type IdeaExtensionCitation,
  type IdeaExtensionResponse,
} from '../services/aiService';
import { usePdfDocumentProcessing, type PdfStage } from '../hooks/usePdfDocumentProcessing';

const Screen24IdeaExtension = () => {
  const { navigate } = useAppRouter();
  const [idea, setIdea] = useState('');
  const [result, setResult] = useState<IdeaExtensionResponse | null>(null);
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
      return await extendIdea(text.trim());
    },
    maxChars: 100_000,
  });

  const handleTextRun = async () => {
    if (!idea.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(await extendIdea(idea.trim()));
    } catch (nextError) {
      setError(userFacingMessage(nextError instanceof Error ? nextError.message : '', 'Unable to extend the idea right now. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handlePdfRun = async () => {
    if (!file) return;
    setError('');
    setResult(null);
    const nextResult = await processPdfAnalysis();
    if (
      nextResult &&
      typeof nextResult === 'object' &&
      'extended_idea' in nextResult
    ) {
      setResult(nextResult as IdeaExtensionResponse);
    }
  };

  const isTextBusy = loading || pdfBusy;

  return (
    <AuthenticatedLayout title="Idea Extension">
      <div className="mx-auto max-w-3xl space-y-6">
        <Card className="p-6">
          <h2 className="text-xl font-bold text-slate-900">Extend a Research Idea</h2>
          <p className="mt-2 text-sm text-slate-600">
            Paste your research idea or upload a PDF. The system will extract the
            document text and generate extensions based on its content.
          </p>

          {/* Mode selector */}
          <div className="mt-6 flex gap-2 border-b border-slate-200 pb-2">
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

          {/* Text input mode */}
          {mode === 'text' && (
            <div className="mt-6">
              <textarea
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                rows={6}
                className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Describe your research idea…"
              />
              <Button
                className="mt-4"
                disabled={isTextBusy || !idea.trim()}
                onClick={handleTextRun}
              >
                {isTextBusy ? 'Analyzing evidence…' : 'Generate Extensions'}
              </Button>
            </div>
          )}

          {/* PDF upload mode */}
          {mode === 'pdf' && (
            <div className="mt-6 space-y-4">
              <label
                htmlFor="idea-extension-pdf"
                className="text-sm font-medium text-slate-700 mb-2 block"
              >
                PDF document
              </label>
              <div className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm flex items-center gap-3">
                <input
                  id="idea-extension-pdf"
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
                {pdfBusy ? 'Analyzing PDF…' : 'Generate extensions'}
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
                        PDF analyzed. Results below.
                      </p>
                      {scanInfo && scanInfo.scannedPages > 0 && (
                        <p className="mt-1 text-xs text-amber-700 bg-amber-50/50 p-2 rounded">
                          {scanInfo.scannedPages} of {scanInfo.totalPages} page(s)
                          could not be extracted (scanned or image-based). Extension
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

          {error && (
            <p role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
              {error}
            </p>
          )}
        </Card>

        {result && result.extended_idea && (
          <Card className="whitespace-pre-wrap p-6 leading-7 text-slate-700">
            {result.extended_idea}
          </Card>
        )}

        {result && result.citations.length > 0 && (
          <Card className="p-6">
            <h3 className="text-sm font-bold text-slate-900 mb-3">
              Source references
            </h3>
            <div className="space-y-3">
              {result.citations.map((citation: IdeaExtensionCitation, index) => (
                <div
                  key={index}
                  className="rounded-md border border-slate-100 p-3 text-sm text-slate-600"
                >
                  <p className="mb-1 italic">“{citation.text_snippet}”</p>
                  <p className="text-xs text-slate-500">
                    Thesis {citation.backend_thesis_id}
                    {citation.page_number !== null ? ` · page ${citation.page_number}` : ''}
                    {citation.relevance_score !== undefined ? ` · relevance ${(citation.relevance_score * 100).toFixed(0)}%` : ''}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        )}

        {pdfBusy && result === null && (
          <Card className="p-4 bg-slate-50 border border-slate-200">
            <p className="text-sm text-slate-600">{pdfProgress}</p>
          </Card>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen24IdeaExtension;