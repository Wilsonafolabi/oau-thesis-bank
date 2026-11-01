import React, { useState } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import { ApiError } from '../lib/api';
import { checkSimilarityText } from '../services/aiService';
import { SIMILARITY_REPORT_KEY } from './Screen23';

const Screen22IdeaChecker = () => {
  const [ideaText, setIdeaText] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { navigate } = useAppRouter();

  const handleCheckText = async () => {
    if (!ideaText.trim()) return;
    setLoading(true);
    setError('');
    try {
      const report = await checkSimilarityText(ideaText.trim());
      sessionStorage.setItem(SIMILARITY_REPORT_KEY, JSON.stringify(report));
      navigate('idea-similarity');
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('You do not have access to one or more compared documents.');
      } else if (err instanceof ApiError && err.status === 503) {
        setError(err.detail || 'Semantic comparison is unavailable right now.');
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Similarity check failed.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthenticatedLayout title="Research Idea Checker">
      <div className="mx-auto max-w-3xl space-y-6">
        <Card className="p-6">
          <h2 className="text-2xl font-bold text-slate-900">Check research similarity</h2>
          <p className="mt-2 text-sm text-slate-600">
            Paste your research idea to compare it against thesis text in the OAU
            repository. Only documents you are authorised to read are compared.
          </p>

          <div className="mt-6">
            <label
              htmlFor="similarity-text"
              className="text-sm font-medium text-slate-700 mb-2 block"
            >
              Research idea text
            </label>
            <textarea
              id="similarity-text"
              value={ideaText}
              onChange={(event) => setIdeaText(event.target.value)}
              rows={6}
              className="mt-2 w-full rounded-md border border-slate-300 p-3 text-sm"
              placeholder="Describe your proposed research idea…"
            />
            <p className="mt-1 text-xs text-slate-500">
              Compared as 200-word passages: exact, near-exact and partial wording overlap,
              plus semantic similarity where the vector index is available. PDF upload is not
              supported by this endpoint — paste the extracted text instead.
            </p>
          </div>

          <div className="mt-6 space-y-2">
            <Button
              className="mt-4"
              disabled={loading || !ideaText.trim()}
              onClick={handleCheckText}
            >
              {loading ? 'Checking similarity…' : 'Check similarity'}
            </Button>
            {error && (
              <p role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
                {error}
              </p>
            )}
          </div>
        </Card>

        <Card className="p-6 bg-slate-50 border border-slate-200">
          <p className="text-sm text-slate-600">
            Similarity is an indicator for review, not a plagiarism finding. Use the
            plagiarism assessment screen for attribution-aware analysis.
          </p>
        </Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;
