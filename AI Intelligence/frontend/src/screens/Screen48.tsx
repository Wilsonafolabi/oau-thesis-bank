import React, { useState } from 'react';
import { BookOpen, Check, ChevronLeft, ChevronRight, FileCheck2, Search, Send, X } from 'lucide-react';
import { AuthenticatedLayout, Badge, Button, Card, useAppRouter } from '../components/shared';
import { ErrorState, LoadingState } from '../components/AsyncState';
import { useApi } from '../hooks/useApi';
import { listAdminSubmissions, reviewAdminSubmission, toArray } from '../lib/api';
import { formatApiError, formatDateTime, formatStatus } from '../lib/formatters';
import type { AdminSubmission, Paginated } from '../types/api';

const Screen48SubmissionReview = () => {
  const { navigate } = useAppRouter();
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const { data, loading, error, refetch } = useApi(
    () => listAdminSubmissions({ q: query || undefined, page }),
    [query, page], true,
  );
  const items = data ? toArray(data) : [];
  const pageInfo = data && !Array.isArray(data) ? data as Paginated<AdminSubmission> : null;

  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setQuery(searchInput.trim());
    setPage(1);
  };

  const decide = async (item: AdminSubmission, decision: 'approved' | 'changes_requested' | 'rejected') => {
    const note = comments[item.id]?.trim() || '';
    if (decision !== 'approved' && !note) {
      setMessage('Add feedback before requesting changes or rejecting a submission.');
      return;
    }
    setBusyId(item.id);
    setMessage('');
    try {
      await reviewAdminSubmission(item.id, decision, note);
      setComments((existing) => { const next = { ...existing }; delete next[item.id]; return next; });
      await refetch();
    } catch (nextError) {
      setMessage(formatApiError(nextError, 'The review decision could not be saved.'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AuthenticatedLayout title="Submission Review" admin>
      <div className="mx-auto max-w-7xl space-y-6 pb-10">
        <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div><Badge variant="gold">Publication workflow</Badge><h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Submission review</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">Review new theses and resubmissions. Approval publishes the record; requests for changes and rejections require feedback for the author.</p></div>
          <div className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"><FileCheck2 className="h-5 w-5 text-amber-700" /><div><p className="text-lg font-bold text-amber-950">{pageInfo?.count ?? items.length}</p><p className="text-[11px] text-amber-800">Awaiting review</p></div></div>
        </section>

        <Card className="p-4 sm:p-5">
          <form onSubmit={submitSearch} className="flex gap-2"><label className="relative min-w-0 flex-1"><span className="sr-only">Search submissions</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search title, author, email, department" className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-[#00502F] focus:ring-2 focus:ring-emerald-100" /></label><Button type="submit">Search</Button></form>
        </Card>

        {message && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{message}</div>}
        {loading ? <LoadingState label="Loading submissions…" /> : error ? <ErrorState message={formatApiError(error, 'Unable to load submissions for review.')} onRetry={() => void refetch()} /> : items.length === 0 ? (
          <Card className="p-12 text-center"><span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-[#00502F]"><Check className="h-6 w-6" /></span><h3 className="mt-4 text-lg font-bold text-slate-900">Review queue is clear</h3><p className="mx-auto mt-1 max-w-md text-sm text-slate-500">New uploads and resubmissions will appear here when they’re ready for review.</p></Card>
        ) : (
          <div className="space-y-4">
            {items.map((item) => {
              const priorReview = item.review_history?.[0];
              const busy = busyId === item.id;
              return <Card key={item.id} className="p-5 sm:p-6">
                <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2"><Badge variant="gold">Pending review</Badge>{item.access_policy === 'public' && <Badge variant="green">Public after approval</Badge>}<span className="text-xs text-slate-400">Submitted {formatDateTime(item.created_at)}</span></div>
                    <h3 className="mt-3 text-xl font-bold leading-snug text-slate-900">{item.title}</h3>
                    <p className="mt-1 text-sm text-slate-600">{item.author} · Submitted by {item.owner_name} ({item.owner_email})</p>
                    <p className="mt-1 text-xs text-slate-500">{[item.department, item.faculty, item.year].filter(Boolean).join(' · ') || 'No department details provided'} · Access: {formatStatus(item.access_policy)}</p>
                    {item.abstract && <p className="mt-4 line-clamp-4 whitespace-pre-line text-sm leading-6 text-slate-600">{item.abstract}</p>}
                    {!!item.tags?.length && <div className="mt-3 flex flex-wrap gap-1.5">{item.tags.map((tag) => <span key={tag} className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">{tag}</span>)}</div>}
                    {priorReview?.comments && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-[10px] font-bold uppercase tracking-wider text-amber-800">Previous review · {formatStatus(priorReview.decision)}</p><p className="mt-1 whitespace-pre-line text-sm leading-6 text-amber-950">{priorReview.comments}</p><p className="mt-2 text-[11px] text-amber-800">{priorReview.reviewer_name || 'Admin'} · {formatDateTime(priorReview.created_at)}</p></div>}
                    <Button variant="secondary" size="sm" className="mt-4" onClick={() => navigate('pdf-reader', { thesisId: item.id })}><BookOpen className="mr-1.5 h-4 w-4" />Open submitted PDF</Button>
                  </div>
                  <div className="w-full shrink-0 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 xl:w-[330px]">
                    <label className="block text-xs font-semibold text-slate-600">Review feedback<textarea value={comments[item.id] || ''} onChange={(event) => setComments((existing) => ({ ...existing, [item.id]: event.target.value }))} rows={4} maxLength={10000} placeholder="Required when requesting changes or rejecting. Tell the author what to update." className="mt-1.5 w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-800 outline-none focus:border-[#00502F] focus:ring-2 focus:ring-emerald-100" /></label>
                    <p className="text-[11px] leading-5 text-slate-500">{item.processing_status === 'failed' ? 'AI indexing failed; the PDF can still be reviewed.' : `Document indexing: ${formatStatus(item.processing_status)}`}</p>
                    <div className="grid grid-cols-1 gap-2"><Button disabled={busy} onClick={() => void decide(item, 'approved')}><Check className="mr-1.5 h-4 w-4" />{busy ? 'Saving…' : 'Approve & publish'}</Button><Button variant="secondary" disabled={busy} onClick={() => void decide(item, 'changes_requested')}><Send className="mr-1.5 h-4 w-4" />Request changes</Button><Button variant="danger" disabled={busy} onClick={() => void decide(item, 'rejected')}><X className="mr-1.5 h-4 w-4" />Reject submission</Button></div>
                  </div>
                </div>
              </Card>;
            })}
            {pageInfo && <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3"><p className="text-xs text-slate-500">Page {page} · {pageInfo.count} pending</p><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={!pageInfo.previous || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronLeft className="mr-1 h-4 w-4" />Previous</Button><Button variant="secondary" size="sm" disabled={!pageInfo.next || loading} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight className="ml-1 h-4 w-4" /></Button></div></div>}
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen48SubmissionReview;
