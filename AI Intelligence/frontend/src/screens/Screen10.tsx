import React, { useState, useCallback } from 'react';
import { AuthenticatedLayout, Badge, Button, Card, useAppRouter } from '../components/shared';
import { apiErrorMessage } from '../lib/api';
import { summarizeThesis, askThesisQuestion, type ThesisQAResponse } from '../services/aiService';

const Screen10ThesisAISummary = () => {
  const { currentScreen, navigate } = useAppRouter();
  const thesisId = Number(currentScreen.params?.thesisId || currentScreen.params?.id);
  const [summary, setSummary] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<ThesisQAResponse['citations']>([]);
  const [insufficientEvidence, setInsufficientEvidence] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const generateSummary = async () => {
    if (!thesisId) {
      setError('No thesis was selected.');
      return;
    }
    setLoading(true);
    setError('');
    setAnswer('');
    setCitations([]);
    setInsufficientEvidence(false);
    try {
      const data = await summarizeThesis(thesisId);
      setSummary(data.summary || '');
    } catch (nextError) {
      setError(apiErrorMessage(nextError, 'Unable to generate the summary.'));
    } finally {
      setLoading(false);
    }
  };

  const askQuestion = useCallback(async () => {
    if (!thesisId) {
      setError('No thesis was selected.');
      return;
    }
    if (!question.trim()) {
      setError('Please enter a question.');
      return;
    }
    setSubmitting(true);
    setError('');
    setAnswer('');
    setCitations([]);
    setInsufficientEvidence(false);
    try {
      const data = await askThesisQuestion({
        backend_thesis_id: String(thesisId),
        question: question.trim(),
        scope: 'this_thesis',
        top_k: 5,
      });
      setAnswer(data.answer || '');
      setCitations(data.citations || []);
      setInsufficientEvidence(!!data.insufficient_evidence);
      if (data.message) {
        setError(data.message);
      }
    } catch (nextError) {
      setError(apiErrorMessage(nextError, 'Unable to answer the question.'));
    } finally {
      setSubmitting(false);
    }
  }, [thesisId, question]);

  return (
    <AuthenticatedLayout title="AI Thesis Q&A">
      <div className="mx-auto max-w-5xl space-y-6">
        <button onClick={() => navigate('thesis-detail', { thesisId })} className="text-sm text-slate-600 hover:text-slate-900">
          ← Back to Thesis
        </button>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Summary card */}
          <Card className="p-6 lg:col-span-3">
            <h2 className="text-xl font-bold text-slate-900">Thesis #{thesisId || '—'}</h2>
            <p className="mt-2 text-sm text-slate-500">
              The summary and Q&A are generated only from indexed thesis evidence.
            </p>
            <div className="flex gap-3 mt-5">
              <Button className="mt-5" disabled={loading || !thesisId} onClick={() => void generateSummary()}>
                {loading ? 'Analyzing…' : 'Generate AI Summary'}
              </Button>
              <Button className="mt-5" variant="secondary" disabled={loading || !thesisId} onClick={() => void setSummary('')}>
                Clear Summary
              </Button>
            </div>
            {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700" role="alert">{error}</p>}
            {summary && (
              <Card className="p-6 mt-4">
                <h3 className="mb-3 text-lg font-bold text-slate-900">Summary</h3>
                <div className="whitespace-pre-wrap leading-7 text-slate-700">{summary}</div>
              </Card>
            )}
          </Card>

          {/* Q&A card */}
          <Card className="p-6 lg:col-span-3">
            <h2 className="text-xl font-bold text-slate-900 mb-4">Ask a Question</h2>
            <p className="text-sm text-slate-500 mb-6">
              Ask about this thesis. Answers are grounded in retrieved thesis passages with citations.
            </p>
            <div className="flex flex-col gap-3">
              <label className="text-sm font-medium text-slate-700">Your question</label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. What is the main methodology used in this thesis?"
                rows={3}
                className="px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-1 focus:ring-[#00502F] focus:border-[#00502F] sm:text-sm text-slate-900 placeholder-slate-400"
                disabled={submitting || !thesisId}
                maxLength={5000}
              />
              <div className="flex gap-2">
                <Button
                  className="mt-5"
                  disabled={submitting || !thesisId || !question.trim()}
                  onClick={() => void askQuestion()}
                >
                  {submitting ? 'Thinking…' : 'Ask Question'}
                </Button>
                <Button className="mt-5" variant="secondary" disabled={submitting} onClick={() => {
                  setQuestion('');
                  setAnswer('');
                  setCitations([]);
                  setInsufficientEvidence(false);
                  setError('');
                }}>
                  Clear
                </Button>
              </div>
              {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700" role="alert">{error}</p>}
              {insufficientEvidence && !error && (
                <p className="rounded-md bg-amber-50 p-4 text-sm text-amber-700" role="alert">
                  Insufficient evidence to answer this question from the thesis content.
                </p>
              )}
              {answer && (
                <Card className="p-6 mt-4">
                  <h3 className="mb-3 text-lg font-bold text-slate-900">Answer</h3>
                  <div className="whitespace-pre-wrap leading-7 text-slate-700 mb-4">{answer}</div>
                  {citations.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-bold text-slate-800">Sources</h4>
                      <div className="space-y-2">
                        {citations.map((citation, idx) => (
                          <Card key={citation.chunk_id} className="p-3 border-slate-200 bg-slate-50">
                            <p className="text-sm text-slate-700 mb-1">{citation.text_snippet}</p>
                            <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                              <span>Page {citation.page_number ?? '—'}</span>
                              <span>Chunk #{citation.chunk_id.slice(-6)}</span>
                              <Badge variant="blue">Relevance: {(citation.relevance_score * 100).toFixed(0)}%</Badge>
                            </div>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}
                  {!citations.length && !insufficientEvidence && answer && (
                    <p className="text-sm text-slate-500 mt-2">No citations returned for this answer.</p>
                  )}
                </Card>
              )}
            </div>
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen10ThesisAISummary;
