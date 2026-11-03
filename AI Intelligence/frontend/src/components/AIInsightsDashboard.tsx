import React, { useEffect, useState } from 'react';
import { detectGaps, getRecommendations } from '../services/aiService';
import type { Recommendation, ResearchGap } from '../services/aiService';

const AIInsightsDashboard: React.FC<{ userId: string }> = ({ userId }) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recommendationNote, setRecommendationNote] = useState<string | null>(null);
  const [gaps, setGaps] = useState<ResearchGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        setError(null);
        const [gapList, recs] = await Promise.all([
          detectGaps(),
          getRecommendations({ top_k: 5 }),
        ]);
        setGaps(gapList);
        setRecommendations(recs.recommendations);
        setRecommendationNote(recs.insufficient_evidence ? recs.message : null);
      } catch (err) {
        console.error("Failed to load AI insights:", err);
        setError("Unable to load AI insights. Please ensure the backend and AI service are running.");
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [userId]);

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 rounded w-1/3"></div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 rounded w-1/3"></div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-600 font-medium">?? {error}</p>
        <p className="text-sm text-red-500 mt-1">Make sure the Django backend is running and the AI service is reachable.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
      {/* Recommendations Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <span className="text-blue-500"></span> AI Recommendations
        </h2>
        {recommendations.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-4xl mb-2"></div>
            <p className="text-gray-500 dark:text-gray-400">
              {recommendationNote || 'No recommendations yet.'}
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
              Recommendations use your stated research interests and repository evidence.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {recommendations.map((rec, idx) => (
              <li key={idx}
                  className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg"
                  >
                <div className="flex justify-between items-center gap-2">
                  <span className="font-medium text-gray-800 dark:text-gray-200 truncate flex-1">
                    {rec.title}
                  </span>
                  <span className="text-xs px-2 py-1 rounded-full whitespace-nowrap bg-blue-100 text-blue-800">
                    {(rec.evidence_strength * 100).toFixed(0)}% match
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {rec.explanation}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Research Gaps Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <span className="text-purple-500">??</span> Research Gaps
        </h2>
        {gaps.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-4xl mb-2"></div>
            <p className="text-gray-500 dark:text-gray-400">No significant research gaps detected yet.</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Upload more theses to enable gap detection analysis.</p>
          </div>
        ) : (
          <ul className="space-y-3 max-h-96 overflow-y-auto">
            {gaps.map((gap, idx) => (
              <li key={idx} className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-purple-50 dark:hover:bg-gray-600 transition">
                <div className="font-semibold capitalize text-gray-800 dark:text-gray-200 mb-1">
                  {gap.gap_type?.replace(/_/g, ' ') || gap.description || 'Research gap'}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  <span className="font-medium">Evidence:</span> {gap.source_thesis_references?.length ?? 0} source(s) · confidence {Math.round((gap.confidence ?? 0) * 100)}%
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-red-600 dark:text-red-400 font-medium bg-red-100 dark:bg-red-900/30 px-2 py-1 rounded">
                    {gap.source_origin === 'author_stated' ? 'Author-stated' : 'System-inferred'}
                  </span>
                  <span className="text-xs text-gray-500">Gap #{idx + 1}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default AIInsightsDashboard;
