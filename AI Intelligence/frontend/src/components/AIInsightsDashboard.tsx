import React, { useEffect, useState } from 'react';
import { getRecommendations, detectGaps, logInteraction, Recommendation, ResearchGap } from '../services/aiService';

const AIInsightsDashboard: React.FC<{ userId: string }> = ({ userId }) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [gaps, setGaps] = useState<ResearchGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        setError(null);
        const [recs, gapData] = await Promise.all([
          getRecommendations(userId),
          detectGaps()
        ]);
        setRecommendations(recs);
        setGaps(gapData);
      } catch (err) {
        console.error("Failed to load AI insights:", err);
        setError("Unable to load AI insights. Please ensure the AI service is running on port 8888.");
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [userId]);

  const handleViewThesis = async (thesisId: string) => {
    try {
      await logInteraction(userId, thesisId, "view");
      // Refresh recommendations after logging interaction
      const updatedRecs = await getRecommendations(userId);
      setRecommendations(updatedRecs);
    } catch (err) {
      console.error("Failed to log interaction:", err);
    }
  };

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
        <p className="text-sm text-red-500 mt-1">Make sure your FastAPI backend is running: <code className="bg-red-100 px-2 py-1 rounded">uvicorn main:app --reload --port 8888</code></p>
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
            <p className="text-gray-500 dark:text-gray-400">No recommendations yet.</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Interact with more theses to get personalized recommendations!</p>
          </div>
        ) : (
          <ul className="space-y-3">
            {recommendations.map((rec, idx) => (
              <li key={idx} 
                  className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-blue-50 dark:hover:bg-gray-600 transition cursor-pointer"
                  onClick={() => handleViewThesis(rec.thesis_id)}>
                <span className="font-medium text-gray-800 dark:text-gray-200 truncate flex-1 mr-2">
                  {rec.thesis_id.replace('_', ' ').toUpperCase()}
                </span>
                <span className={`text-xs px-2 py-1 rounded-full whitespace-nowrap ${
                  rec.source === 'learned_model' 
                    ? 'bg-green-100 text-green-800' 
                    : 'bg-blue-100 text-blue-800'
                }`}>
                  {rec.source === 'learned_model' ? 'Learned' : 'Baseline'}
                </span>
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
                <div className="font-semibold text-gray-800 dark:text-gray-200 mb-1">
                  {gap.topic_name}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  <span className="font-medium">Keywords:</span> {gap.representative_keywords.join(', ')}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-red-600 dark:text-red-400 font-medium bg-red-100 dark:bg-red-900/30 px-2 py-1 rounded">
                    Only {gap.document_count} thesis(es) - Under-researched
                  </span>
                  <span className="text-xs text-gray-500">Topic #{gap.topic_id}</span>
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