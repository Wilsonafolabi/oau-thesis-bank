import React, { useEffect, useRef, useState } from 'react';
import { CheckCircle, Loader2, RefreshCw } from 'lucide-react';
import { useAppRouter, Button, Card, AuthenticatedLayout, UploadWizardNav, Badge } from '../components/shared';
import { useUpload } from '../context/UploadContext';
import { useApi } from '../hooks/useApi';
import { apiErrorMessage, getThesis } from '../lib/api';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { formatStatus } from '../lib/formatters';
import { getAIDocumentJob } from '../services/aiService';
import type { JobResponse } from '../types/api';

const ACTIVE_PROCESSING_STATES = new Set(['queued', 'processing']);
const MAX_POLLS = 20;

const Screen18PublishConfirmation = () => {
  const { navigate, currentScreen } = useAppRouter();
  const { submittedThesisId } = useUpload();
  const id = Number(currentScreen.params?.thesisId || submittedThesisId);
  const aiJobId = typeof currentScreen.params?.aiJobId === 'string' ? currentScreen.params.aiJobId : '';
  const initialAIError = typeof currentScreen.params?.aiError === 'string' ? currentScreen.params.aiError : '';
  const { data: thesis, loading, error, refetch } = useApi(() => id ? getThesis(id) : Promise.resolve(null), [id], true);
  const polls = useRef(0);
  const [aiJob, setAIJob] = useState<JobResponse | null>(null);
  const [aiError, setAIError] = useState(initialAIError);

  useEffect(() => { polls.current = 0; }, [id]);
  useEffect(() => {
    if (!thesis || loading || !ACTIVE_PROCESSING_STATES.has(thesis.processing_status) || polls.current >= MAX_POLLS) return undefined;
    const timer = window.setTimeout(() => { polls.current += 1; void refetch(); }, 3000);
    return () => window.clearTimeout(timer);
  }, [thesis?.processing_status, loading, refetch]);

  useEffect(() => {
    if (!aiJobId) return undefined;
    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;
    const poll = async () => {
      try {
        const nextJob = await getAIDocumentJob(aiJobId);
        if (cancelled) return;
        setAIJob(nextJob);
        if (ACTIVE_PROCESSING_STATES.has(nextJob.status) && attempts < MAX_POLLS) {
          attempts += 1;
          timer = window.setTimeout(() => void poll(), 3000);
        }
      } catch (nextError) {
        if (!cancelled) setAIError(apiErrorMessage(nextError, 'AI indexing status is unavailable.'));
      }
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [aiJobId]);

  if (!id) return <AuthenticatedLayout title="Submission Received"><EmptyState title="No submitted thesis" description="Submit a thesis through the upload flow before opening this screen." /></AuthenticatedLayout>;
  if (loading && !thesis) return <AuthenticatedLayout title="Submission Received"><LoadingState label="Confirming your submission…" /></AuthenticatedLayout>;
  if (error || !thesis) return <AuthenticatedLayout title="Submission Received"><ErrorState message={apiErrorMessage(error, 'Unable to confirm your submission.')} onRetry={() => void refetch()} /></AuthenticatedLayout>;
  const processing = ACTIVE_PROCESSING_STATES.has(thesis.processing_status);
  return <AuthenticatedLayout title="Submission Received"><div className="mx-auto mt-10 max-w-2xl text-center"><UploadWizardNav step={5} /><div className={`mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full ${processing ? 'bg-amber-100' : 'bg-emerald-100'}`}>{processing ? <Loader2 className="h-10 w-10 animate-spin text-amber-600" /> : <CheckCircle className="h-10 w-10 text-emerald-600" />}</div><Badge variant={thesis.status === 'published' ? 'green' : 'gold'}>{formatStatus(thesis.status)}</Badge><h2 className="mb-4 mt-4 text-3xl font-bold text-slate-900">{thesis.status === 'pending_review' ? 'Your submission is awaiting review' : processing ? 'Your document is processing' : 'Your research was submitted'}</h2><p className="mb-8 text-lg text-slate-600">{thesis.title}</p><Card className="mb-4 bg-slate-50 p-6 text-left"><div className="flex items-center justify-between gap-4"><h4 className="font-medium text-slate-900">Submission status</h4><button onClick={() => void refetch()} className="inline-flex items-center text-xs font-semibold text-[#00502F] hover:text-[#003d24]"><RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh</button></div><p className="mt-2 text-sm text-slate-600">Review status: <strong>{formatStatus(thesis.status)}</strong>. Admin approval controls publication. Document indexing runs separately.</p><p className="mt-1 text-sm text-slate-600">Indexing status: <strong>{formatStatus(thesis.processing_status)}</strong>.</p>{polls.current >= MAX_POLLS && processing && <p className="mt-3 text-xs text-amber-700">Automatic checks paused. Refresh when you want to check again.</p>}</Card>{(aiJobId || aiError) && <Card className="mb-8 p-6 text-left"><h4 className="font-medium text-slate-900">AI document indexing</h4>{aiError ? <p className="mt-2 text-sm text-amber-800">{aiError}</p> : <><p className="mt-2 text-sm text-slate-600">Status: <strong>{aiJob?.status || 'pending'}</strong>. {aiJob?.message || 'Waiting for the AI service.'}</p>{aiJob?.status === 'completed' && <p className="mt-2 text-sm text-emerald-700">Indexed {String(aiJob.result?.chunks ?? 0)} evidence chunks.</p>}</>}</Card>}<div className="flex flex-col justify-center gap-3 sm:flex-row"><Button variant="secondary" onClick={() => navigate('my-projects')}>View my projects</Button><Button onClick={() => navigate('thesis-detail', { thesisId: thesis.id })}>Go to thesis page</Button></div></div></AuthenticatedLayout>;
};

export default Screen18PublishConfirmation;
