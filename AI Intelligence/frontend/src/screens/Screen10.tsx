import React, { useState, useEffect } from 'react';
import { AuthenticatedLayout, useAppRouter } from '../components/shared';

const Screen10ThesisAISummary = () => {
  const { navigate } = useAppRouter();
  const [thesis, setThesis] = useState<any>(null);
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(true);
  const [summarizing, setSummarizing] = useState(false);

  // Get ID from URL
  const searchId = new URLSearchParams(window.location.search).get('thesisId');
  const pathId = window.location.pathname.split('/').pop();
  const id = pathId !== 'ai' ? pathId : searchId;

  useEffect(() => {
    const fetchThesis = async () => {
      try {
        const token = localStorage.getItem('access') || localStorage.getItem('token');
        const headers: any = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`http://localhost:8000/api/theses/${id}/`, { headers });
        if (res.ok) {
          const data = await res.json();
          setThesis(data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    if (id) fetchThesis();
  }, [id]);

  const generateSummary = async () => {
    if (!thesis) return;
    setSummarizing(true);
    setSummary('');
    try {
      const token = localStorage.getItem('access') || localStorage.getItem('token');
      const headers: any = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      // Ask the AI to summarize based on the title and abstract
      const prompt = `Please provide a detailed academic summary of the thesis titled "${thesis.title}". Abstract: ${thesis.abstract || 'No abstract provided'}. Include key methodologies and potential impact.`;
      
      const res = await fetch('http://localhost:8000/api/ai/rag-query', {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: prompt })
      });
      
      const data = await res.json();
      setSummary(data.answer || 'Summary generation failed.');
    } catch (err) {
      setSummary('Error connecting to AI.');
    }
    setSummarizing(false);
  };

  if (loading) return <AuthenticatedLayout title="Loading..."><div className="p-8 text-center">Loading...</div></AuthenticatedLayout>;
  if (!thesis) return <AuthenticatedLayout title="Not Found"><div className="p-8 text-center">Thesis not found.</div></AuthenticatedLayout>;

  return (
    <AuthenticatedLayout title={`AI Summary: ${thesis.title}`}>
      <div className="max-w-4xl mx-auto p-6">
        <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 mb-6">
          <h2 className="text-xl font-bold mb-2">{thesis.title}</h2>
          <p className="text-slate-600 mb-4">by {thesis.author || 'Unknown Author'}</p>
          
          <button 
            onClick={generateSummary} 
            disabled={summarizing}
            className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:opacity-50 flex items-center gap-2"
          >
            {summarizing ? 'AI is reading...' : '? Generate AI Summary'}
          </button>
        </div>

        {summary && (
          <div className="bg-slate-50 p-6 rounded-lg border border-slate-200">
            <h3 className="text-lg font-bold mb-3 text-slate-800">AI Analysis</h3>
            <p className="text-slate-700 leading-relaxed whitespace-pre-wrap">{summary}</p>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen10ThesisAISummary;