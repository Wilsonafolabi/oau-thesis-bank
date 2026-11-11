import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Search, UserRoundCog } from 'lucide-react';
import { AuthenticatedLayout, Badge, Button, Card, useAppRouter } from '../components/shared';
import { ErrorState, LoadingState } from '../components/AsyncState';
import { useApi } from '../hooks/useApi';
import { listAdminUsers, toArray, updateAdminUserAccess } from '../lib/api';
import { formatApiError, formatDate, formatStatus, initials } from '../lib/formatters';
import type { AdminUser, Paginated, UserRole, UserStatus } from '../types/api';

type UserDraft = { role: UserRole; status: UserStatus };

const Screen45 = () => {
  const { user: currentUser } = useAppRouter();
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ tone: 'error' | 'success'; text: string } | null>(null);
  const { data, loading, error, refetch } = useApi(
    () => listAdminUsers({ search: search || undefined, role: role || undefined, status: status || undefined, page }),
    [search, role, status, page], true,
  );

  const users = data ? toArray(data) : [];
  const pageInfo = data && !Array.isArray(data) ? data as Paginated<AdminUser> : null;
  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); setSearch(searchInput.trim()); setPage(1); };
  const changeFilter = (update: () => void) => { update(); setPage(1); };
  const getDraft = (record: AdminUser): UserDraft => drafts[record.id] || { role: record.role, status: record.status };
  const setDraft = (record: AdminUser, patch: Partial<UserDraft>) => setDrafts((existing) => ({
    ...existing,
    [record.id]: { ...getDraft(record), ...patch },
  }));
  const saveAccess = async (record: AdminUser) => {
    const draft = getDraft(record);
    const payload: Partial<UserDraft> = {};
    if (draft.role !== record.role) payload.role = draft.role;
    if (draft.status !== record.status) payload.status = draft.status;
    if (!Object.keys(payload).length) return;
    setBusyId(record.id);
    setMessage(null);
    try {
      await updateAdminUserAccess(record.id, payload);
      setDrafts((existing) => { const next = { ...existing }; delete next[record.id]; return next; });
      setMessage({ tone: 'success', text: `Access updated for ${record.name || record.email}.` });
      await refetch();
    } catch (nextError) {
      setMessage({ tone: 'error', text: formatApiError(nextError, 'Could not update this account.') });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AuthenticatedLayout title="User Management" admin>
      <div className="mx-auto max-w-7xl space-y-6 pb-10">
        <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div><Badge variant="green">Access control</Badge><h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">User management</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">Find an account, review its affiliation, and update its platform role or access status.</p></div>
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-[#00502F]"><UserRoundCog className="h-5 w-5" /></span><div><p className="text-lg font-bold text-slate-900">{pageInfo?.count ?? users.length}</p><p className="text-[11px] text-slate-500">Accounts found</p></div></div>
        </section>

        <Card className="p-4 sm:p-5">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_190px_190px]">
            <form onSubmit={submitSearch} className="flex gap-2"><label className="relative min-w-0 flex-1"><span className="sr-only">Search accounts</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search name or email" className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-[#00502F] focus:ring-2 focus:ring-emerald-100" /></label><Button type="submit">Search</Button></form>
            <label className="text-xs font-semibold text-slate-500">Role<select value={role} onChange={(event) => changeFilter(() => setRole(event.target.value))} className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-800"><option value="">All roles</option><option value="student">Student</option><option value="researcher">Researcher</option><option value="faculty">Faculty</option><option value="admin">Admin</option></select></label>
            <label className="text-xs font-semibold text-slate-500">Account status<select value={status} onChange={(event) => changeFilter(() => setStatus(event.target.value))} className="mt-1.5 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-800"><option value="">All statuses</option><option value="active">Active</option><option value="pending">Pending</option><option value="suspended">Suspended</option></select></label>
          </div>
        </Card>

        {message && <div role={message.tone === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-4 py-3 text-sm ${message.tone === 'error' ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>{message.text}</div>}
        {loading ? <LoadingState label="Loading accounts…" /> : error ? <ErrorState message={formatApiError(error, 'Unable to load user accounts.')} onRetry={() => void refetch()} /> : users.length === 0 ? (
          <Card className="p-12 text-center"><Search className="mx-auto h-9 w-9 text-slate-300" /><h3 className="mt-4 text-lg font-bold text-slate-900">No accounts found</h3><p className="mt-1 text-sm text-slate-500">Adjust the search or filters and try again.</p></Card>
        ) : (
          <>
            <Card className="overflow-hidden">
              <div className="hidden overflow-x-auto md:block">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50"><tr>{['Account', 'Affiliation', 'Role', 'Status', 'Joined', ''].map((heading) => <th key={heading} className="px-5 py-3 text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">{heading}</th>)}</tr></thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {users.map((record) => {
                      const draft = getDraft(record);
                      const changed = draft.role !== record.role || draft.status !== record.status;
                      const isSelf = record.id === currentUser?.id;
                      return <tr key={record.id} className="hover:bg-slate-50/70">
                        <td className="px-5 py-4"><div className="flex min-w-[220px] items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-emerald-50 text-xs font-bold text-[#00502F]">{record.avatar ? <img src={record.avatar} alt="" className="h-full w-full object-cover" /> : initials(record.name || record.email)}</span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900">{record.name || 'Unnamed account'}{isSelf && <span className="ml-2 text-[10px] font-medium text-slate-400">You</span>}</p><p className="truncate text-xs text-slate-500">{record.email}</p></div></div></td>
                        <td className="px-5 py-4"><p className="text-sm text-slate-700">{record.department || '—'}</p><p className="mt-0.5 text-xs text-slate-400">{record.faculty || 'No faculty set'}</p></td>
                        <td className="px-5 py-4"><select aria-label={`Role for ${record.email}`} value={draft.role} disabled={isSelf || busyId === record.id} onChange={(event) => setDraft(record, { role: event.target.value as UserRole })} className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 disabled:bg-slate-50"><option value="student">Student</option><option value="researcher">Researcher</option><option value="faculty">Faculty</option><option value="admin">Admin</option></select></td>
                        <td className="px-5 py-4"><select aria-label={`Status for ${record.email}`} value={draft.status} disabled={(isSelf && record.status === 'active') || busyId === record.id} onChange={(event) => setDraft(record, { status: event.target.value as UserStatus })} className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 disabled:bg-slate-50"><option value="active">Active</option><option value="pending">Pending</option><option value="suspended">Suspended</option></select></td>
                        <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">{formatDate(record.joined)}</td>
                        <td className="whitespace-nowrap px-5 py-4 text-right"><Button size="sm" variant={changed ? 'primary' : 'secondary'} disabled={!changed || busyId === record.id} onClick={() => void saveAccess(record)}>{busyId === record.id ? 'Saving…' : 'Save'}</Button></td>
                      </tr>;
                    })}
                  </tbody>
                </table>
              </div>
              <div className="divide-y divide-slate-100 md:hidden">
                {users.map((record) => {
                  const draft = getDraft(record);
                  const changed = draft.role !== record.role || draft.status !== record.status;
                  const isSelf = record.id === currentUser?.id;
                  return <div key={record.id} className="space-y-4 p-4">
                    <div className="flex items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-xs font-bold text-[#00502F]">{record.avatar ? <img src={record.avatar} alt="" className="h-full w-full rounded-full object-cover" /> : initials(record.name || record.email)}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-900">{record.name || 'Unnamed account'}{isSelf ? ' · You' : ''}</p><p className="truncate text-xs text-slate-500">{record.email}</p></div><Badge variant={draft.status === 'active' ? 'green' : 'gray'}>{formatStatus(draft.status)}</Badge></div>
                    <p className="text-xs text-slate-500">{[record.department, record.faculty].filter(Boolean).join(' · ') || 'No affiliation set'}</p>
                    <div className="grid grid-cols-2 gap-3"><label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Role<select value={draft.role} disabled={isSelf || busyId === record.id} onChange={(event) => setDraft(record, { role: event.target.value as UserRole })} className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-700"><option value="student">Student</option><option value="researcher">Researcher</option><option value="faculty">Faculty</option><option value="admin">Admin</option></select></label><label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Status<select value={draft.status} disabled={(isSelf && record.status === 'active') || busyId === record.id} onChange={(event) => setDraft(record, { status: event.target.value as UserStatus })} className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-700"><option value="active">Active</option><option value="pending">Pending</option><option value="suspended">Suspended</option></select></label></div>
                    <div className="flex items-center justify-between"><span className="text-xs text-slate-400">Joined {formatDate(record.joined)}</span><Button size="sm" disabled={!changed || busyId === record.id} onClick={() => void saveAccess(record)}>{busyId === record.id ? 'Saving…' : 'Save changes'}</Button></div>
                  </div>;
                })}
              </div>
            </Card>
            {pageInfo && <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3"><p className="text-xs text-slate-500">Page {page} · {pageInfo.count} total accounts</p><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={!pageInfo.previous || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}><ChevronLeft className="mr-1 h-4 w-4" />Previous</Button><Button variant="secondary" size="sm" disabled={!pageInfo.next || loading} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight className="ml-1 h-4 w-4" /></Button></div></div>}
          </>
        )}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen45;
