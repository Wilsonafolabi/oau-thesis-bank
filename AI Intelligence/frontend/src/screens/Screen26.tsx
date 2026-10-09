import React, { useEffect, useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { detectGaps } from '../services/aiService';

const Screen26GapAnalysis = () => {
  const { currentScreen, navigate } = useAppRouter();
  const topic = String(currentScreen.params?.topic || '');
  const [gap, setGap] = useState<any>(null);
  const [loading, setLoading] = useState(Boolean(topic));
  const [error, setError] = useState('');

  useEffect(() => {
    if (!topic) return;
    setLoading(true);
    detectGaps(topic)
      .then((gaps) => setGap(gaps.find((item) => item.topic_name === topic) || gaps[0] || null))
      .catch((nextError) => setError(nextError instanceof Error ? nextError.message : 'Unable to load gap analysis.'))
      .finally(() => setLoading(false));
  }, [topic]);

  return (
    <AuthenticatedLayout title="Gap Analysis">
      <div className="mx-auto max-w-3xl">
        {!topic ? (
          <Card className="p-8 text-center">
            <p className="text-slate-600">Select a candidate gap from the Gap Explorer.</p>
            <Button className="mt-4" onClick={() => navigate('gap-explorer')}>Open Gap Explorer</Button>
          </Card>
        ) : loading ? (
          <Card className="p-8">Analyzing corpus evidence…</Card>
        ) : error ? (
          <Card className="p-8 text-red-700">{error}</Card>
        ) : gap ? (
          <Card className="p-6">
            <h2 className="text-2xl font-bold text-slate-900">{gap.topic_name}</h2>
            <p className="mt-2 text-slate-600">{gap.interpretation}</p>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="rounded-md bg-slate-50 p-4"><span className="text-xs text-slate-500">Documents</span><p className="mt-1 text-xl font-bold">{gap.document_count}</p></div>
              <div className="rounded-md bg-slate-50 p-4"><span className="text-xs text-slate-500">Method</span><p className="mt-1 font-bold">{gap.method}</p></div>
            </div>
            <p className="mt-6 text-sm text-slate-500">This is a candidate gap signal, not a claim that no prior work exists.</p>
          </Card>
        ) : (
          <Card className="p-8">No matching corpus evidence was found.</Card>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen26GapAnalysis;
