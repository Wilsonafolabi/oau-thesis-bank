import { Activity, ArrowRight, CheckCircle2, ClipboardList, Database, FileText, HardDrive, Users } from 'lucide-react';
import { AuthenticatedLayout, Badge, Button, Card, useAppRouter } from '../components/shared';
import { ErrorState, LoadingState } from '../components/AsyncState';
import { useApi } from '../hooks/useApi';
import { getAdminActivity, getAdminHealth, getAdminSummary, toArray } from '../lib/api';
import { formatApiError, formatCount, formatDateTime, formatStatus } from '../lib/formatters';

const Screen43AdminDashboard = () => {
  const { navigate, user } = useAppRouter();
  const { data, loading, error, refetch } = useApi(async () => Promise.all([
    getAdminSummary(), getAdminActivity(8), getAdminHealth(),
  ]), [], true);

  if (loading) return <AuthenticatedLayout title="Admin Overview" admin><LoadingState label="Loading platform operations…" /></AuthenticatedLayout>;
  if (error || !data) return <AuthenticatedLayout title="Admin Overview" admin><ErrorState message={formatApiError(error, 'Unable to load admin operations.')} onRetry={() => void refetch()} /></AuthenticatedLayout>;

  const [summary, activityPayload, health] = data;
  const activity = toArray(activityPayload);
  const stats = [
    { icon: FileText, label: 'Total theses', value: summary.total_theses, note: `${formatCount(summary.published_theses)} published` },
    { icon: Users, label: 'Active users', value: summary.active_users, note: `${formatCount(summary.total_users)} accounts` },
    { icon: ClipboardList, label: 'Pending submissions', value: summary.pending_review_theses, note: 'Needs publication review', alert: summary.pending_review_theses > 0 },
    { icon: ClipboardList, label: 'Access requests', value: summary.pending_access_requests, note: 'Waiting for a decision' },
  ];
  const serviceChecks = [
    { icon: Database, label: 'Database', status: health.checks.db },
    { icon: HardDrive, label: 'File storage', status: health.checks.storage },
  ];

  return (
    <AuthenticatedLayout title="Admin Overview" admin>
      <div className="mx-auto max-w-7xl space-y-6 pb-10">
        <section className="flex flex-col justify-between gap-5 rounded-2xl bg-[#00502F] p-6 text-white sm:flex-row sm:items-end sm:p-8">
          <div>
            <div className="flex items-center gap-2"><Badge variant="gold">Operations center</Badge><span className="text-xs text-emerald-100">Signed in as {user?.name || user?.email}</span></div>
            <h2 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">Good to see you, {user?.name?.split(' ')[0] || 'Admin'}.</h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-emerald-100">Review new theses, keep content standards high, and manage platform access.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => navigate('admin-submissions')}><ClipboardList className="mr-2 h-4 w-4" /> Submission queue</Button>
            <Button className="bg-[#D4AF37] text-slate-950 hover:bg-yellow-400 focus:ring-[#D4AF37]" onClick={() => navigate('user-management')}><Users className="mr-2 h-4 w-4" /> Manage users</Button>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.map(({ icon: Icon, label, value, note, alert }) => (
            <Card key={label} className="p-5">
              <div className="flex items-start justify-between"><span className="rounded-xl bg-emerald-50 p-2.5 text-[#00502F]"><Icon className="h-5 w-5" /></span>{alert && <Badge variant="gold">Action needed</Badge>}</div>
              <p className="mt-5 text-3xl font-bold tracking-tight text-slate-900">{formatCount(value)}</p>
              <p className="mt-1 text-sm font-semibold text-slate-700">{label}</p>
              <p className="mt-1 text-xs text-slate-500">{note}</p>
            </Card>
          ))}
        </section>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.9fr_1.4fr]">
          <Card className="p-5 sm:p-6">
            <div className="flex items-start justify-between"><div><h3 className="font-bold text-slate-900">Platform health</h3><p className="mt-1 text-xs text-slate-500">Live checks for core services</p></div><Activity className="h-5 w-5 text-slate-400" /></div>
            <div className="mt-5 space-y-3">
              {serviceChecks.map(({ icon: Icon, label, status }) => (
                <div key={label} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                  <span className="flex items-center gap-3 text-sm font-medium text-slate-700"><Icon className="h-4 w-4 text-slate-400" />{label}</span>
                  <span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${status === 'ok' ? 'text-emerald-700' : 'text-red-600'}`}><span className={`h-1.5 w-1.5 rounded-full ${status === 'ok' ? 'bg-emerald-500' : 'bg-red-500'}`} />{status === 'ok' ? 'Operational' : 'Needs attention'}</span>
                </div>
              ))}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-emerald-50 p-4"><p className="text-xs text-emerald-800">Published theses</p><p className="mt-1 text-xl font-bold text-[#00502F]">{formatCount(summary.published_theses)}</p></div>
              <div className="rounded-xl bg-amber-50 p-4"><p className="text-xs text-amber-800">Suspended accounts</p><p className="mt-1 text-xl font-bold text-amber-900">{formatCount(summary.suspended_users)}</p></div>
            </div>
            <button onClick={() => navigate('university-analytics')} className="mt-5 flex w-full items-center justify-between border-t border-slate-100 pt-4 text-left text-sm font-semibold text-[#00502F] hover:text-emerald-800">Open research analytics<ArrowRight className="h-4 w-4" /></button>
          </Card>

          <Card className="p-5 sm:p-6">
            <div className="flex items-start justify-between"><div><h3 className="font-bold text-slate-900">Recent admin activity</h3><p className="mt-1 text-xs text-slate-500">Latest recorded changes across the platform</p></div><Activity className="h-5 w-5 text-slate-400" /></div>
            {activity.length === 0 ? (
              <div className="mt-8 rounded-xl border border-dashed border-slate-200 p-8 text-center"><CheckCircle2 className="mx-auto h-8 w-8 text-slate-300" /><p className="mt-3 text-sm font-semibold text-slate-700">No activity recorded yet</p><p className="mt-1 text-xs text-slate-500">Admin and review actions will appear here.</p></div>
            ) : (
              <div className="mt-4 divide-y divide-slate-100">
                {activity.map((event) => (
                  <div key={event.id} className="flex gap-3 py-3.5 first:pt-1 last:pb-1">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-[#00502F]"><Activity className="h-4 w-4" /></span>
                    <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-x-2 gap-y-1"><p className="text-sm font-semibold text-slate-800">{formatStatus(event.action)}</p><span className="text-xs text-slate-400">{formatDateTime(event.created_at)}</span></div><p className="mt-1 truncate text-xs text-slate-500">{event.actor_name || 'System'}{event.detail ? ` · ${event.detail}` : ''}</p></div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen43AdminDashboard;
