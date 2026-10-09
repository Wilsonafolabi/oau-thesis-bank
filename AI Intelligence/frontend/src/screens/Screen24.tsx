import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card } from '../components/shared';
import { extendIdea } from '../services/aiService';

const Screen24IdeaExtension = () => {
  const [idea, setIdea] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const run = async () => {
    if (!idea.trim()) return;
    setLoading(true);
    setError('');
    try {
      const data = await extendIdea(idea.trim());
      setResult(data.suggestions || data.message || '');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to extend the idea.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="Idea Extension">
      <div className="mx-auto max-w-3xl space-y-5">
        <Card className="p-6">
          <h2 className="text-xl font-bold">Extend a Research Idea</h2>
          <textarea value={idea} onChange={(e) => setIdea(e.target.value)} rows={6} className="mt-4 w-full rounded-md border border-slate-300 p-3" placeholder="Describe your research idea…" />
          <Button className="mt-4" disabled={loading || !idea.trim()} onClick={() => void run()}>
            {loading ? 'Analyzing evidence…' : 'Generate Extensions'}
          </Button>
        </Card>
        {error && <p className="rounded-md bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        {result && <Card className="whitespace-pre-wrap p-6 leading-7 text-slate-700">{result}</Card>}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen24IdeaExtension;
