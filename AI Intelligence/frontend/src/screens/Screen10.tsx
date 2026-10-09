import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { apiErrorMessage } from '../lib/api';
import { summarizeThesis } from '../services/aiService';

const Screen10ThesisAISummary = () => {
  const { currentScreen, navigate } = useAppRouter();
  const thesisId = Number(currentScreen.params?.thesisId || currentScreen.params?.id);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const generateSummary = async () => {
    if (!thesisId) {
      setError('No thesis was selected.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = await summarizeThesis(thesisId);
      setSummary(data.summary || '');
    } catch (nextError) {
      setError(apiErrorMessage(nextError, 'Unable to generate the summary.'));
    } finally {
      setLoading(false);
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
          <Button className="mt-5" disabled={loading || !thesisId} onClick={() => void generateSummary()}>
            {loading ? 'Analyzing…' : 'Generate AI Summary'}
          </Button>
        </Card>
        {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700" role="alert">{error}</p>}
        {summary && (
          <Card className="p-6">
            <h3 className="mb-3 text-lg font-bold text-slate-900">Summary</h3>
            <div className="whitespace-pre-wrap leading-7 text-slate-700">{summary}</div>
          </Card>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen10ThesisAISummary;
