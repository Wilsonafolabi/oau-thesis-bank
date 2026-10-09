import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { checkSimilarity, type SimilarityReport } from '../services/aiService';

const Screen22IdeaChecker = () => {
  const { navigate } = useAppRouter();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<SimilarityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCheck = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const report = await checkSimilarity(file);
      sessionStorage.setItem('oau:lastSimilarityReport', JSON.stringify(report));
      setResult(report);
      navigate('idea-similarity');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Similarity check failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="Research Idea Checker">
      <div className="mx-auto max-w-3xl space-y-6">
        <Card className="p-6">
          <h2 className="text-2xl font-bold text-slate-900">Check Research Similarity</h2>
          <p className="mt-2 text-sm text-slate-600">
            Upload a PDF. The AI service compares it with indexed thesis chunks and returns evidence.
          </p>
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="mt-5 block w-full rounded-md border border-slate-300 p-3 text-sm"
          />
          <Button className="mt-4" disabled={!file || loading} onClick={() => void handleCheck()}>
            {loading ? 'Analyzing…' : 'Check Similarity'}
          </Button>
        </Card>
        {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        {result && (
          <Card className="p-6">
            <p className="font-semibold text-slate-900">
              {result.flagged_chunks_count || 0} potentially similar chunks found
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {result.chunks_scanned || 0} chunks scanned at threshold {result.threshold_used}
            </p>
          </Card>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;
