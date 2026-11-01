import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { detectGaps } from '../services/aiService';

const formatGapType = (value?: string) =>
  value ? value.replace(/_/g, ' ') : 'candidate gap';

const Screen25GapExplorer = () => {
  const { navigate } = useAppRouter();
  const [input, setInput] = useState('');
  const [gaps, setGaps] = useState<Awaited<ReturnType<typeof detectGaps>>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleExplore = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError('');
    try {
      setGaps(await detectGaps(input.trim()));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Gap detection failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="Research Gap Explorer">
      <div className="mx-auto max-w-4xl space-y-5">
        <Card className="p-6">
          <h2 className="text-2xl font-bold text-slate-900">Explore Research Gaps</h2>
          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={4} className="mt-4 w-full rounded-md border border-slate-300 p-3" placeholder="Enter a research topic…" />
          <Button className="mt-4" disabled={loading || !input.trim()} onClick={() => void handleExplore()}>
            {loading ? 'Analyzing corpus…' : 'Find Candidate Gaps'}
          </Button>
        </Card>
        {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        <div className="space-y-4">
          {gaps.map((gap, index) => (
            <Card
              key={`${gap.gap_type}-${index}`}
              className="cursor-pointer p-5 hover:shadow-md"
              onClick={() => navigate('gap-detail', { topic: gap.gap_type })}
            >
              <div className="flex items-center justify-between gap-4">
                <h3 className="font-bold capitalize text-slate-900">{formatGapType(gap.gap_type)}</h3>
                <span className="text-sm text-slate-500">{gap.source_thesis_references?.length ?? 0} sources</span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {gap.description || gap.explanation || 'Candidate underrepresented area; review the evidence before treating it as a confirmed gap.'}
              </p>
              <p className="mt-2 text-xs text-slate-400">
                Origin: {gap.source_origin || 'system_inferred'} · Confidence: {Math.round((gap.confidence ?? 0) * 100)}%
              </p>
            </Card>
          ))}
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen25GapExplorer;
