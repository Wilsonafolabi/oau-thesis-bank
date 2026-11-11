import React from 'react';
import { AlertCircle, ArrowUpRight, Download, Eye, FileText, Search, Quote, TrendingUp } from 'lucide-react';
import { AuthenticatedLayout, Card } from '../components/shared';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { useApi } from '../hooks/useApi';
import { listMine } from '../lib/api';
import { formatCount } from '../lib/formatters';

const Screen38 = () => {
  const { data, loading, error, refetch } = useApi(() => listMine(), [], true);
  const projects = [...(data || [])].sort((a, b) => (b.views || 0) - (a.views || 0));
  const totalViews = projects.reduce((total, project) => total + (project.views || 0), 0);
  const totalDownloads = projects.reduce((total, project) => total + (project.downloads || 0), 0);
  const topProjects = projects.slice(0, 5);
  const maxViews = Math.max(...topProjects.map((project) => project.views || 0), 1);

  const metrics = [
    { label: 'Total views', value: formatCount(totalViews), note: 'Across your research', icon: Eye, accent: 'border-t-[#00502F]' },
    { label: 'Downloads', value: formatCount(totalDownloads), note: 'Across your research', icon: Download, accent: 'border-t-[#D4AF37]' },
    { label: 'Search appearances', value: '—', note: 'Not provided by the API', icon: Search, accent: 'border-t-slate-300', unavailable: true },
    { label: 'Citations', value: '—', note: 'Not provided by the API', icon: Quote, accent: 'border-t-slate-300', unavailable: true },
  ];

  return (
    <AuthenticatedLayout title="My Research Impact">
      <div className="mx-auto max-w-7xl space-y-6 pb-10">
        <header>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#00502F]">
            <TrendingUp className="h-4 w-4" /> Personal analytics
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">My Research Impact</h2>
          <p className="mt-1 text-sm text-slate-500">Views and downloads across the theses you have uploaded.</p>
        </header>

        {loading ? <LoadingState label="Loading your research impact…" /> : null}
        {error ? <ErrorState message="Unable to load your research analytics." onRetry={() => void refetch()} /> : null}

        {!loading && !error && data && <>
          <section aria-label="Research impact metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map(({ label, value, note, icon: Icon, accent, unavailable }) => (
              <Card key={label} className={`border-t-4 p-5 ${accent}`}>
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
                  <Icon className={`h-4 w-4 ${unavailable ? 'text-slate-300' : 'text-[#00502F]'}`} />
                </div>
                <p className={`mt-3 text-3xl font-bold ${unavailable ? 'text-slate-400' : 'text-slate-900'}`}>{value}</p>
                <p className="mt-1 text-xs text-slate-500">{note}</p>
              </Card>
            ))}
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)]">
            <Card className="min-h-[340px] p-5 sm:p-6">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-emerald-50 p-2 text-[#00502F]"><TrendingUp className="h-5 w-5" /></div>
                <div>
                  <h3 className="font-bold text-slate-900">Views over time</h3>
                  <p className="mt-1 text-xs text-slate-500">Monthly history for your own projects</p>
                </div>
              </div>
              <div className="mt-8 flex min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-6 text-center">
                <AlertCircle className="h-6 w-6 text-slate-400" />
                <p className="mt-3 text-sm font-semibold text-slate-700">Personal view history is not available</p>
                <p className="mt-1 max-w-md text-sm leading-6 text-slate-500">The current API returns lifetime view totals, but not monthly view counts for your projects.</p>
              </div>
            </Card>

            <Card className="p-5 sm:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-bold text-slate-900">Top performing projects</h3>
                  <p className="mt-1 text-xs text-slate-500">Ranked by lifetime views</p>
                </div>
                <FileText className="h-5 w-5 text-slate-400" />
              </div>
              {topProjects.length === 0 ? (
                <div className="mt-6"><EmptyState title="No projects uploaded yet" description="Your research projects will appear here once you upload them." /></div>
              ) : (
                <ol className="mt-6 space-y-5">
                  {topProjects.map((project, index) => (
                    <li key={project.id}>
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-3">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">{index + 1}</span>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-800" title={project.title}>{project.title}</p>
                            <p className="mt-0.5 text-xs text-slate-500">{formatCount(project.downloads || 0)} downloads</p>
                          </div>
                        </div>
                        <span className="shrink-0 text-sm font-bold text-slate-700">{formatCount(project.views || 0)}</span>
                      </div>
                      <div className="ml-9 h-1.5 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-[#00502F]" style={{ width: `${Math.max(((project.views || 0) / maxViews) * 100, 2)}%` }} />
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              {projects.length > 5 && <p className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-500">Showing your 5 most-viewed projects <ArrowUpRight className="inline h-3.5 w-3.5" /></p>}
            </Card>
          </section>
        </>}
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen38;
