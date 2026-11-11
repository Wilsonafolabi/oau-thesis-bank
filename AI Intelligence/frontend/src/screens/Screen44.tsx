import React, { useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import { AuthenticatedLayout, Badge, Button, Card } from '../components/shared';
import { ErrorState, LoadingState } from '../components/AsyncState';
import { useApi } from '../hooks/useApi';
import { listAdminModeration, reviewAdminModeration, toArray } from '../lib/api';
import { formatApiError, formatDateTime, formatStatus } from '../lib/formatters';
import type { AdminFlagType, AdminModerationItem, AdminModerationStatus, Paginated } from '../types/api';

const flagLabels: Record<AdminFlagType, string> = {
  high_similarity: 'High similarity',
  standard_review: 'Standard review',
  metadata: 'Metadata check',
};

const Screen44 = () => {
  const [status, setStatus] = useState<AdminModerationStatus>('pending');
  const [flagType, setFlagType] = useState<AdminFlagType | ''>('');
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState('');
  const { data, loading, error, refetch } = useApi(
    () => listAdminModeration({ status, flag_type: flagType || undefined, q: query || undefined, page }),
    [status, flagType, query, page], true,
  );

  const records = data ? toArray(data) : [];
  const pageInfo = data && !Array.isArray(data) ? data as Paginated<AdminModerationItem> : null;
  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setQuery(searchInput.trim());
    setPage(1);
  };

  const review = async (item: AdminModerationItem, decision: 'approved' | 'dismissed') => {
    setBusyId(item.id);
    setActionError('');
    try {
      await reviewAdminModeration(item.id, decision);
      await refetch();
    } catch (nextError) {
      setActionError(formatApiError(nextError, 'Could not update this moderation item.'));
    } finally {
      setBusyId(null);
    }
  };

  const changeFilter = (update: () => void) => { update(); setPage(1); };

  return (
    <AuthenticatedLayout title="Content Moderation" admin>
      <div className="mx-auto max-w-7xl space-y-6 pb-10">
        <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div><Badge variant="gold">Review workspace</Badge><h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Content moderation</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">Review flagged thesis records and record a clear decision for each report.</p></div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"><p className="text-xs font-medium text-amber-800">Showing</p><p className="mt-0.5 text-lg font-bold text-amber-950">{pageInfo?.count ?? records.length} <span className="text-sm font-medium">records</span></p></div>
        </section>

        <Card className="p-4 sm:p-5">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_190px_190px]">
            <form onSubmit={submitSearch} className="flex gap-2">
              <label className="relative min-w-0 flex-1"><span className="sr-only">Search flagged content</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search title, author, department" className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-[#00502F] focus:ring-2 focus:ring-emerald-100" /></label>
              <Button type="submit">Search</Button>
            </form>
            <label className="text-xs font-semibold text-slate-500">Review status<select value={status} onChange={(event) => changeFilter(() => setStatus(event.target.value as AdminModerationStatus))} className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-800"><option value="pending">Pending</option><option value="approved">Approved</option><option value="dismissed">Dismissed</option></select></label>
            <label className="text-xs font-semibold text-slate-500">Flag type<select value={flagType} onChange={(event) => changeFilter(() => setFlagType(event.target.value as AdminFlagType | ''))} className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-800"><option value="">All flag types</option><option value="high_similarity">High similarity</option><option value="standard_review">Standard review</option><option value="metadata">Metadata</option></select></label>
          </div>
        </Card>

        {actionError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{actionError}</div>}
        {loading ? <LoadingState label="Loading moderation queue…" /> : error ? <ErrorState message={formatApiError(error, 'Unable to load the moderation queue.')} onRetry={() => void refetch()} /> : records.length === 0 ? (
          <Card className="p-12 text-center"><span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-[#00502F]"><Check className="h-6 w-6" /></span><h3 className="mt-4 text-lg font-bold text-slate-900">Queue is clear</h3><p className="mx-auto mt-1 max-w-md text-sm text-slate-500">No records match these filters. Try another status or clear the search.</p></Card>
        ) : (
          <div className="space-y-3">
            {records.map((item) => (
              <ModerationCard key={item.id} item={item} busy={busyId === item.id} onReview={(decision) => void review(item, decision)} />
            ))}
            {pageInfo && <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3"><p className="text-xs text-slate-500">Page {page} · {pageInfo.count} total records</p><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={!pageInfo.previous || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronLeft className="mr-1 h-4 w-4" />Previous</Button><Button variant="secondary" size="sm" disabled={!pageInfo.next || loading} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight className="ml-1 h-4 w-4" /></Button></div></div>}
          </div>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

const ModerationCard = ({ item, busy, onReview }: { item: AdminModerationItem; busy: boolean; onReview: (decision: 'approved' | 'dismissed') => void }) => (
  <Card className="p-5 sm:p-6">
    <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><Badge variant={item.flag_type === 'high_similarity' ? 'gold' : 'blue'}>{flagLabels[item.flag_type] || formatStatus(item.flag_type)}</Badge><Badge variant={item.status === 'pending' ? 'gray' : 'green'}>{formatStatus(item.status)}</Badge><span className="text-xs text-slate-400">Reported {formatDateTime(item.created_at)}</span></div>
        <h3 className="mt-3 text-lg font-bold leading-snug text-slate-900">{item.thesis_title}</h3>
        <p className="mt-1 text-sm text-slate-600">{item.thesis_author}{item.thesis_department ? ` · ${item.thesis_department}` : ''}</p>
        {item.note && <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3"><p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Report note</p><p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700">{item.note}</p></div>}
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500"><span>Reported by {item.reporter_name || 'A platform user'}</span>{item.similarity_score != null && <span>Similarity score {Math.round(item.similarity_score > 1 ? item.similarity_score : item.similarity_score * 100)}%</span>}{item.reviewer_name && <span>Reviewed by {item.reviewer_name}</span>}</div>
      </div>
      {item.status === 'pending' && <div className="flex shrink-0 gap-2 lg:pt-1"><Button variant="secondary" disabled={busy} onClick={() => onReview('dismissed')}><X className="mr-1.5 h-4 w-4" />Dismiss</Button><Button disabled={busy} onClick={() => onReview('approved')}><Check className="mr-1.5 h-4 w-4" />Approve</Button></div>}
    </div>
  </Card>
);

export default Screen44;
