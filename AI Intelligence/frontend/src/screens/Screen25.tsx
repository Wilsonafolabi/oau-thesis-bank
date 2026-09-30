import React, { useState } from 'react';
import { AuthenticatedLayout } from '../components/shared';

const Screen25GapExplorer = () => {
  const [input, setInput] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);

  const handleExplore = async () => {
    if (!input.trim()) return;
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/ai/rag-query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: "What are the research gaps related to: " + input })
      });
      const data = await res.json();
      setResult(data.answer || JSON.stringify(data));
    } catch (e) { setResult('Error connecting to backend.'); }
    setLoading(false);
  };

  return (
    <AuthenticatedLayout title="Research Gap Explorer">
      <div className="p-6 max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-4">Explore Research Gaps</h2>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} className="w-full p-3 border rounded mb-4" rows={4} placeholder="Enter a research topic to find gaps..." />
        <button onClick={handleExplore} disabled={loading} className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:opacity-50">
          {loading ? 'Exploring...' : 'Find Gaps'}
        </button>
        {result && <div className="mt-4 p-4 bg-gray-100 rounded whitespace-pre-wrap">{result}</div>}
      </div>
    </AuthenticatedLayout>
  );
};
export default Screen25GapExplorer;