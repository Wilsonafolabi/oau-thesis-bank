import React from 'react';
import { AuthenticatedLayout } from '../components/shared';

const Screen23SimilarityResults = () => (
  <AuthenticatedLayout title="Similarity Results">
    <div className="flex flex-col items-center justify-center p-12 text-center border border-slate-200 bg-slate-50 rounded-lg max-w-2xl mx-auto mt-10">
      <div className="text-4xl mb-4">??</div>
      <h3 className="text-xl font-bold text-slate-900 mb-2">Similarity Results</h3>
      <p className="text-slate-600 mb-4">Detailed plagiarism and similarity report.</p>
      <span className="px-3 py-1 text-xs font-medium text-blue-800 bg-blue-100 rounded-full">Awaiting Backend Integration</span>
    </div>
  </AuthenticatedLayout>
);

export default Screen23SimilarityResults;