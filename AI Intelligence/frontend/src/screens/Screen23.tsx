import React, { useMemo } from 'react';
import { AuthenticatedLayout, Button, Card, Badge, useAppRouter } from '../components/shared';
import type {
  SimilarityMatch,
  SimilarityMatchType,
  SimilarityResponse,
} from '../services/aiService';

export const SIMILARITY_REPORT_KEY = 'oau:lastSimilarityReport';

const GROUPS: { type: SimilarityMatchType; label: string; note: string }[] = [
  {
    type: 'exact',
    label: 'Exact overlap',
    note: 'The submitted passage appears word-for-word in the source.',
  },
  {
    type: 'near_exact',
    label: 'Near-exact overlap',
    note: 'The passages share most of their wording; only minor edits differ.',
  },
  {
    type: 'partial',
    label: 'Partial overlap',
    note: 'Part of the submitted passage overlaps the source.',
  },
  {
    type: 'semantic',
    label: 'Semantic similarity',
    note: 'Differently worded but semantically close. This is not textual overlap.',
  },
];

const Screen23SimilarityResults = () => {
  const { navigate } = useAppRouter();

  const report = useMemo<SimilarityResponse | null>(() => {
    try {
      const raw = sessionStorage.getItem(SIMILARITY_REPORT_KEY);
      return raw ? (JSON.parse(raw) as SimilarityResponse) : null;
    } catch {
      return null;
    }
  }, []);

  if (!report) {
    return (
      <AuthenticatedLayout title="Similarity Results">
        <div className="mx-auto max-w-5xl space-y-6">
          <Card className="p-8 text-center">
            <h2 className="text-xl font-bold">No similarity report yet</h2>
            <p className="mt-2 text-sm text-slate-500">
              Run the similarity check first to generate a report.
            </p>
            <Button className="mt-5" onClick={() => navigate('idea-checker')}>
              Run check
            </Button>
          </Card>
        </div>
      </AuthenticatedLayout>
    );
  }

  const groups = GROUPS.map((group) => ({
    ...group,
    matches: report.matches.filter((match) => match.match_type === group.type),
  })).filter((group) => group.matches.length > 0);

  return (
    <AuthenticatedLayout title="Similarity Results">
      <div className="mx-auto max-w-5xl space-y-6">
        <Card className="p-6">
          <h2 className="text-xl font-bold text-slate-900">Similarity report</h2>
          <p className="mt-2 text-sm text-slate-500">
            {report.matches.length} match{report.matches.length === 1 ? '' : 'es'} across{' '}
            {report.chunks_scanned} repository chunk{report.chunks_scanned === 1 ? '' : 's'} ·{' '}
            {report.passages_scanned} submitted passage
            {report.passages_scanned === 1 ? '' : 's'} checked
          </p>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="px-2 py-1 bg-slate-100 text-slate-600 rounded">
              Input: {report.input_mode === 'text' ? 'Pasted text' : report.input_mode}
            </span>
            {GROUPS.filter((group) =>
              report.matches.some((match) => match.match_type === group.type),
            ).map((group) => (
              <span key={group.type} className="px-2 py-1 bg-slate-100 text-slate-600 rounded">
                {group.label}:{' '}
                {report.matches.filter((match) => match.match_type === group.type).length}
              </span>
            ))}
          </div>
        </Card>

        <Card className="p-6 bg-amber-50 border border-amber-200">
          <h3 className="text-sm font-bold text-amber-900 mb-2">Important</h3>
          <p className="text-sm text-amber-800 leading-relaxed">
            Overlap is an indicator for human review, not a plagiarism finding. Lexical
            overlap (exact, near-exact, partial) and semantic similarity are different
            signals and are shown separately. Only documents you are authorised to read were
            compared.
          </p>
        </Card>

        {groups.length === 0 ? (
          <Card className="p-8 text-center">
            <p className="text-sm text-slate-500">
              No matches were found above the configured threshold.
            </p>
          </Card>
        ) : (
          groups.map((group) => (
            <div key={group.type}>
              <h3 className="text-lg font-bold text-slate-900">{group.label}</h3>
              <p className="mb-4 text-xs text-slate-500">{group.note}</p>
              <div className="space-y-4">
                {group.matches.map((match: SimilarityMatch, index) => (
                  <Card key={`${match.document_id}-${match.chunk_id}-${index}`} className="p-5">
                    <div className="flex flex-wrap justify-between gap-3 mb-2">
                      <div>
                        <p className="font-semibold text-slate-900">
                          {match.title || `Thesis ${match.backend_thesis_id}`}
                        </p>
                        <p className="text-xs text-slate-500">
                          Thesis {match.backend_thesis_id} · chunk {match.chunk_id}
                          {match.page_number !== null ? ` · page ${match.page_number}` : ''}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="font-semibold text-slate-900">
                          {(match.score * 100).toFixed(1)}%
                        </span>
                        <Badge variant="blue" className="ml-2 text-[10px]">
                          {match.match_type.replace(/_/g, ' ')}
                        </Badge>
                      </div>
                    </div>

                    <div className="mb-3">
                      <span className="text-xs font-medium text-slate-700">Source passage:</span>
                      <p className="mt-1 text-sm italic text-slate-600">{match.source_excerpt}</p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-700">Your text:</span>
                      <p className="mt-1 text-sm text-slate-600">{match.submitted_excerpt}</p>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ))
        )}

        {report.limitations.length > 0 && (
          <Card className="p-6">
            <h3 className="text-sm font-bold text-slate-900 mb-2">Limitations</h3>
            <ul className="text-sm text-slate-600 list-disc list-inside space-y-1">
              {report.limitations.map((limitation, index) => (
                <li key={index}>{limitation}</li>
              ))}
            </ul>
          </Card>
        )}

        <div className="mt-6 flex gap-3">
          <Button onClick={() => navigate('idea-checker')}>Run another check</Button>
          <Button variant="secondary" onClick={() => navigate('idea-extension')}>
            Extend a matched idea
          </Button>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen23SimilarityResults;
