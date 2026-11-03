import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { apiErrorMessage } from '../lib/api';
import {
  summarizeThesis,
  askThesisQuestion,
  type ThesisQAResponse,
} from '../services/aiService';

const SCREEN_TABS: Array<{ id: string; label: string }> = [
  { id: 'summary', label: 'Summary' },
  { id: 'qa', label: 'Ask this thesis' },
];

const Screen10ThesisAISummary = () => {
  const { currentScreen, navigate } = useAppRouter();
  const thesisId = Number(currentScreen.params?.thesisId || currentScreen.params?.id);
  const [activeTab, setActiveTab] = useState<'summary' | 'qa'>('summary');

  // Summary state
  const [summary, setSummary] = useState<string>('');
  const [summaryError, setSummaryError] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);

  // Q&A state
  const [qaQuestion, setQaQuestion] = useState('');
  const [qaResult, setQaResult] = useState<ThesisQAResponse | null>(null);
  const [qaError, setQaError] = useState('');
  const [qaLoading, setQaLoading] = useState(false);

  const generateSummary = async () => {
    if (!thesisId) {
      setSummaryError('No thesis was selected.');
      return;
    }
    setSummaryLoading(true);
    setSummaryError('');
    try {
      const data = await summarizeThesis(thesisId);
      setSummary(data.summary || '');
    } catch (nextError) {
      setSummaryError(apiErrorMessage(nextError, 'Unable to generate the summary.'));
    } finally {
      setSummaryLoading(false);
    }
  };

  const askQuestion = async () => {
    if (!thesisId) {
      setQaError('No thesis was selected.');
      return;
    }
    if (!qaQuestion.trim()) return;
    setQaLoading(true);
    setQaError('');
    setQaResult(null);
    try {
      setQaResult(
        await askThesisQuestion({
          backend_thesis_id: String(thesisId),
          question: qaQuestion.trim(),
          scope: 'this_thesis',
          top_k: 5,
        })
      );
    } catch (nextError) {
      setQaError(apiErrorMessage(nextError, 'Unable to answer the question.'));
    } finally {
      setQaLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="AI Thesis Summary">
      <div className="mx-auto max-w-4xl space-y-6">
        <button onClick={() => navigate('thesis-detail', { thesisId })} className="text-sm text-slate-600 hover:text-slate-900">
          ← Back to Thesis
        </button>
        <Card className="p-6">
          <h2 className="text-xl font-bold text-slate-900">Thesis #{thesisId || '—'}</h2>
          <p className="mt-2 text-sm text-slate-500">
            The summary is generated only from indexed thesis evidence.
          </p>

          {/* Tabs */}
          <div className="mt-6 flex gap-2 border-b border-slate-200 pb-2">
            {SCREEN_TABS.map((tab) => (
              <Button
                key={tab.id}
                variant={activeTab === tab.id ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setActiveTab(tab.id as any)}
              >
                {tab.label}
              </Button>
            ))}
          </div>

          {/* Summary tab */}
          {activeTab === 'summary' && (
            <div className="mt-6 space-y-3">
              <Button
                className="mt-4"
                disabled={summaryLoading || !thesisId}
                onClick={() => void generateSummary()}
              >
                {summaryLoading ? 'Analyzing…' : 'Generate AI Summary'}
              </Button>
              {summaryError && (
                <p className="rounded-md bg-red-50 p-4 text-sm text-red-700" role="alert">
                  {summaryError}
                </p>
              )}
              {summary && (
                <Card className="p-6">
                  <h3 className="mb-3 text-lg font-bold text-slate-900">Summary</h3>
                  <div className="whitespace-pre-wrap leading-7 text-slate-700">{summary}</div>
                </Card>
              )}
            </div>
          )}

          {/* Q&A tab */}
          {activeTab === 'qa' && (
            <div className="mt-6 space-y-4">
              <p className="text-sm text-slate-600">
                Ask a question about this thesis. Answers are grounded in the thesis's own
                indexed text and cite the supporting passages.
              </p>
              <textarea
                value={qaQuestion}
                onChange={(event) => setQaQuestion(event.target.value)}
                rows={4}
                className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm"
                placeholder="Ask a question about this thesis…"
              />
              <Button
                className="mt-4"
                disabled={qaLoading || !qaQuestion.trim() || !thesisId}
                onClick={() => void askQuestion()}
              >
                {qaLoading ? 'Answering…' : 'Ask question'}
              </Button>
              {qaError && (
                <p className="rounded-md bg-red-50 p-4 text-sm text-red-700" role="alert">
                  {qaError}
                </p>
              )}
              {qaResult && (
                <Card className="p-6">
                  <h3 className="mb-3 text-lg font-bold text-slate-900">Answer</h3>
                  <div className="whitespace-pre-wrap leading-7 text-slate-700 mb-4">
                    {qaResult.answer || '(no answer)'}
                  </div>
                  {!qaResult.insufficient_evidence && qaResult.citations.length > 0 && (
                    <div>
                      <h4 className="text-sm font-bold text-slate-900 mb-2">
                        Sources
                      </h4>
                      <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
                        {qaResult.citations.map((citation, index) => (
                          <li key={index}>
                            {citation.text_snippet}
                            {citation.page_number !== null ? ` (page ${citation.page_number})` : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {qaResult.insufficient_evidence && (
                    <p className="text-sm text-amber-700 bg-amber-50/50 p-2 rounded">
                      {qaResult.message || 'Insufficient evidence to answer with confidence.'}
                    </p>
                  )}
                </Card>
              )}
              {qaLoading && qaResult === null && (
                <p className="text-sm text-slate-500">Answering…</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen10ThesisAISummary;