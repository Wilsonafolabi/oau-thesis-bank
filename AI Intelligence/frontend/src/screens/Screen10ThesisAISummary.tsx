import React, { useState } from 'react';
import { AuthenticatedLayout, useAppRouter } from '../components/shared';

const Screen10ThesisAISummary = () => {
  const { navigate } = useAppRouter();
  
  // Get the REAL data passed from Screen 09
  const storedThesis = sessionStorage.getItem('currentThesis');
  const thesis = storedThesis ? JSON.parse(storedThesis) : null;
  
  const [summary, setSummary] = useState('');
  const [summarizing, setSummarizing] = useState(false);

  const generateSummary = async () => {
    if (!thesis) return;
    setSummarizing(true);
    setSummary('');
    
    try {
      // Send the REAL title and abstract to your FastAPI backend
      const res = await fetch('http://localhost:8888/api/ai/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          title: thesis.title || "Untitled Thesis", 
          abstract: thesis.abstract || "" 
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        setSummary(data.summary);
      } else {
        setSummary('AI service error. Make sure FastAPI is running on port 8888.');
      }
    } catch (err) {
      setSummary('Error connecting to AI service.');
    }
    setSummarizing(false);
  };

  if (!thesis) {
    return (
      <AuthenticatedLayout title="Error">
        <div className="p-8 text-center text-red-600">
          No thesis data found. Please go back and click "AI Summary" from the Thesis Details page.
          <br/>
          <button onClick={() => navigate('thesis-detail')} className="mt-4 text-blue-600 underline">Go Back</button>
        </div>
      </AuthenticatedLayout>
    );
  }

  return (
    <AuthenticatedLayout title={AI Summary: }>
      <div className="max-w-4xl mx-auto p-6">
        <button 
          onClick={() => navigate('thesis-detail', { thesisId: thesis.id })}
          className="mb-4 text-slate-600 hover:text-slate-900 flex items-center gap-1"
        >
          ? Back to Thesis Details
        </button>

        <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 mb-6">
          <h2 className="text-2xl font-bold mb-2 text-slate-900">{thesis.title}</h2>
          <p className="text-slate-600 mb-4">by {thesis.author || 'Unknown Author'}</p>
          
          <button 
            onClick={generateSummary} 
            disabled={summarizing}
            className="bg-[#00502F] text-white px-6 py-2 rounded hover:bg-[#003d23] disabled:opacity-50 flex items-center gap-2 font-medium transition-colors"
          >
            {summarizing ? '? AI is analyzing your document...' : '? Generate NotebookLM Summary'}
          </button>
        </div>

        {summary && (
          <div className="bg-slate-50 p-8 rounded-lg border border-slate-200">
            <div className="whitespace-pre-wrap text-slate-800 leading-relaxed text-[15px]">{summary}</div>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen10ThesisAISummary;