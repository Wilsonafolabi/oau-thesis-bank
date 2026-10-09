import React, { useMemo } from 'react';
import { AuthenticatedLayout, Button, Card, useAppRouter } from '../components/shared';
import type { SimilarityReport } from '../services/aiService';

const Screen23SimilarityResults = () => {
  const { navigate } = useAppRouter();
  const report = useMemo<SimilarityReport | null>(() => {
    try {
      const raw = sessionStorage.getItem('oau:lastSimilarityReport');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }, []);

  return (
    <AuthenticatedLayout title="Similarity Results">
      <div className="mx-auto max-w-5xl space-y-6">
        {!report ? (
          <Card className="p-8 text-center">
            <h2 className="text-xl font-bold">No similarity report yet</h2>
            <p className="mt-2 text-sm text-slate-500">Run the research idea checker first.</p>
            <Button className="mt-5" onClick={() => navigate('idea-checker')}>Run Check</Button>
          </Card>
        ) : (
          <>
            <Card className="p-6">
              <h2 className="text-xl font-bold text-slate-900">Similarity Report</h2>
              <p className="mt-2 text-sm text-slate-500">
                {report.flagged_chunks_count || 0} flagged chunks / {report.chunks_scanned || 0} scanned.
              </p>
            </Card>
            <div className="space-y-4">
              {(report.flagged_chunks || []).map((match, index) => (
                <Card key={`${match.document_id}-${match.matched_page}-${index}`} className="p-5">
                  <div className="flex flex-wrap justify-between gap-3">
                    <p className="font-semibold text-slate-900">
                      {match.document_id} · page {match.matched_page}
                    </p>
                    <span className="font-semibold text-[#00502F]">
                      {(match.similarity_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{match.text_preview}</p>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen23SimilarityResults;
