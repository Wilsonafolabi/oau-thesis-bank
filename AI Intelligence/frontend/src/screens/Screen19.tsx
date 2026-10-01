import React, { useEffect, useRef, useState } from 'react';
import { Lock, PlusCircle, Trash2, Unlock } from 'lucide-react';
import { useAppRouter, Button, Card, Badge, AuthenticatedLayout } from '../components/shared';
import { useApi } from '../hooks/useApi';
import { apiErrorMessage, deleteThesis, listMine } from '../lib/api';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { formatDate, formatStatus } from '../lib/formatters';

const Screen19MyProjects = () => {
  const { navigate } = useAppRouter();
  const { data, loading, error, refetch } = useApi(listMine, [], true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: number; title: string } | null>(null);
  const [actionError, setActionError] = useState('');
  const deletingRef = useRef(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pendingDelete) return undefined;
    dialogRef.current?.querySelector('button')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !deletingRef.current) setPendingDelete(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [pendingDelete]);

  const remove = async () => {
    if (!pendingDelete) return;
    const { id } = pendingDelete;
    deletingRef.current = true;
    setDeletingId(id);
    setActionError('');
    try {
      await deleteThesis(id);
      setPendingDelete(null);
      await refetch();
    } catch (nextError) {
      setActionError(apiErrorMessage(nextError, 'Unable to delete this project.'));
    } finally {
      deletingRef.current = false;
      setDeletingId(null);
    }
  };

  return (
    <AuthenticatedLayout title="My Research Projects">
      <div className="mb-6 flex justify-end">
        <Button onClick={() => navigate('upload')}><PlusCircle className="mr-2 h-4 w-4" /> Upload new</Button>
      </div>
      {loading && <LoadingState label="Loading your projects…" />}
      {error && <ErrorState onRetry={() => void refetch()} />}
      {!loading && !error && (!data || data.length === 0) && (
        <EmptyState title="No projects yet" description="Upload a thesis to start building your research workspace." />
      )}
      {!loading && !error && data && data.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>{['Project title', 'Status', 'Access', 'Date', 'Actions'].map((heading) => <th key={heading} className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500">{heading}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {data.map((thesis) => (
                  <tr
                    key={thesis.id}
                    tabIndex={0}
                    aria-label={`Open project ${thesis.title}`}
                    onClick={() => navigate('thesis-detail', { thesisId: thesis.id })}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget || (event.key !== 'Enter' && event.key !== ' ')) return;
                      event.preventDefault();
                      navigate('thesis-detail', { thesisId: thesis.id });
                    }}
                    className="cursor-pointer hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-[#00502F]"
                  >
                    <td className="px-6 py-4">
                      <span className="line-clamp-1 text-left text-sm font-medium text-slate-900">{thesis.title}</span>
                      <div className="text-xs text-slate-500">{thesis.department || 'Department not provided'}</div>
                    </td>
                    <td className="whitespace-nowrap px-6 py-4">
                      <Badge variant={thesis.status === 'published' ? 'green' : 'gray'}>{formatStatus(thesis.status)}</Badge>
                      <div className="mt-1 text-xs text-slate-400">{formatStatus(thesis.processing_status)}</div>
                    </td>
                    <td className="flex items-center whitespace-nowrap px-6 py-4 text-sm text-slate-500">
                      {thesis.access_policy === 'public' ? <Unlock className="mr-1 h-3 w-3" /> : <Lock className="mr-1 h-3 w-3" />}{formatStatus(thesis.access_policy)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-slate-500">{formatDate(thesis.created_at)}</td>
                    <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                      <button onClick={(event) => { event.stopPropagation(); navigate('edit-thesis', { thesisId: thesis.id }); }} className="mr-4 text-[#00502F] hover:text-[#003d24]">Edit</button>
                      <button
                        aria-label={`Delete ${thesis.title}`}
                        onClick={(event) => { event.stopPropagation(); setActionError(''); setPendingDelete({ id: thesis.id, title: thesis.title }); }}
                        className="inline-flex items-center text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" /> Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {pendingDelete && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4"
          onMouseDown={(event) => { if (event.target === event.currentTarget && !deletingRef.current) setPendingDelete(null); }}
        >
          <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="delete-project-title" aria-describedby="delete-project-description" className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-xl">
            <h2 id="delete-project-title" className="text-lg font-semibold text-slate-900">Delete this project?</h2>
            <p id="delete-project-description" className="mt-2 break-words text-sm leading-6 text-slate-600">
              “{pendingDelete.title}” will be permanently deleted. This action cannot be undone.
            </p>
            {actionError && <p className="mt-4 text-sm text-red-600" role="alert">{actionError}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" disabled={deletingId !== null} onClick={() => setPendingDelete(null)}>Cancel</Button>
              <Button variant="danger" disabled={deletingId !== null} onClick={() => void remove()}>
                <Trash2 className="mr-2 h-4 w-4" /> {deletingId !== null ? 'Deleting…' : 'Delete project'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </AuthenticatedLayout>
  );
};

export default Screen19MyProjects;
