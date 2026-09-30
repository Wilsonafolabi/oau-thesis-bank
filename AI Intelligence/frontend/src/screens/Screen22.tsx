import React, { useState } from 'react';
import { AuthenticatedLayout } from '../components/shared';

const Screen22IdeaChecker = () => {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('http://localhost:8000/api/ai/check-similarity', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      setResult(data);
    } catch (e) { 
      setResult({ status: 'error', message: 'Error connecting to backend.' }); 
    }
    setLoading(false);
  };

  return (
    <AuthenticatedLayout title="Research Idea Checker">
      <div className="p-6 max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-2 text-slate-900">Check Document Similarity</h2>
        <p className="mb-6 text-slate-600">Upload a research proposal or thesis draft to check its similarity against existing work.</p>
        
        <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 mb-6">
          <input 
            type="file" 
            accept=".pdf,.txt,.doc,.docx"
            onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)} 
            className="w-full p-3 border border-slate-300 rounded-md mb-4 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-green-500" 
          />
          
          <button 
            onClick={handleCheck} 
            disabled={loading || !file} 
            className="w-full bg-green-600 text-white px-6 py-3 rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {loading ? 'Analyzing Document...' : 'Check Similarity'}
          </button>
        </div>
        
        {result && (
          <div className={`p-6 rounded-lg border ${result.status === 'success' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-start gap-4">
              <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${result.status === 'success' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                {result.status === 'success' ? '?' : '?'}
              </div>
              <div className="flex-1">
                <h3 className={`text-lg font-bold mb-1 ${result.status === 'success' ? 'text-green-900' : 'text-red-900'}`}>
                  {result.status === 'success' ? 'Analysis Complete' : 'Analysis Failed'}
                </h3>
                <p className={`text-sm mb-3 ${result.status === 'success' ? 'text-green-700' : 'text-red-700'}`}>
                  {file ? `File analyzed: ${file.name}` : ''}
                </p>
                <p className="text-slate-700 text-sm whitespace-pre-wrap">{result.message || JSON.stringify(result)}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;