import React, { useEffect, useState } from 'react';
import { ArrowLeft, FileUp } from 'lucide-react';
import { useAppRouter, Button, Input, Card, AuthenticatedLayout } from '../components/shared';
import { useApi } from '../hooks/useApi';
import { apiErrorMessage, getThesis, replaceThesisFile, updateThesis } from '../lib/api';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { formatFileSize, normalizeTags } from '../lib/formatters';

const MAX_PDF_SIZE = 10 * 1024 * 1024;

const Screen20EditThesis = () => {
  const { navigate, currentScreen } = useAppRouter();
  const thesisId = Number(currentScreen.params?.thesisId || currentScreen.params?.id);
  const { data: thesis, loading, error, refetch } = useApi(() => thesisId ? getThesis(thesisId) : Promise.resolve(null), [thesisId], true);
  const [form, setForm] = useState({ title: '', author: '', department: '', faculty: '', year: '', supervisor: '', abstract: '', tags: '' });
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [replacementFile, setReplacementFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState('');

  useEffect(() => {
    if (thesis) setForm({
      title: thesis.title,
      author: thesis.author,
      department: thesis.department,
      faculty: thesis.faculty,
      year: thesis.year ? String(thesis.year) : '',
      supervisor: thesis.supervisor,
      abstract: thesis.abstract,
      tags: thesis.tags.join(', '),
    });
  }, [thesis]);

  if (!thesisId) return <AuthenticatedLayout title="Edit Thesis Metadata"><EmptyState title="No thesis selected" description="Choose a project before editing its metadata." /></AuthenticatedLayout>;
  if (loading) return <AuthenticatedLayout title="Edit Thesis Metadata"><LoadingState label="Loading thesis…" /></AuthenticatedLayout>;
  if (error || !thesis) return <AuthenticatedLayout title="Edit Thesis Metadata"><ErrorState message={apiErrorMessage(error, 'Unable to load this thesis.')} onRetry={() => void refetch()} /></AuthenticatedLayout>;
  if (!['draft', 'changes_requested'].includes(thesis.status)) return <AuthenticatedLayout title="Edit Thesis Metadata"><Card className="mx-auto max-w-2xl p-8"><h2 className="text-xl font-bold text-slate-900">This submission is locked</h2><p className="mt-2 text-sm leading-6 text-slate-600">You can edit a draft or a submission returned with requested changes. This record is currently {thesis.status.replaceAll('_', ' ')}.</p><Button className="mt-5" onClick={() => navigate('my-projects')}>Back to my projects</Button></Card></AuthenticatedLayout>;

  const save = async () => {
    if (!form.title.trim()) { setMessage('A title is required.'); return; }
    setSaving(true);
    setMessage('');
    setFileError('');
    try {
      await updateThesis(thesis.id, {
        title: form.title.trim(),
        author: form.author.trim(),
        department: form.department.trim(),
        faculty: form.faculty.trim(),
        year: form.year ? Number(form.year) : null,
        supervisor: form.supervisor.trim(),
        abstract: form.abstract,
        tags: normalizeTags(form.tags),
      });
      if (replacementFile) await replaceThesisFile(thesis.id, replacementFile);
      navigate('my-projects');
    } catch (nextError) {
      setMessage(apiErrorMessage(nextError, 'Unable to save changes.'));
    } finally {
      setSaving(false);
    }
  };

  const chooseReplacement = (file?: File) => {
    if (!file) return;
    if (!(file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))) {
      setFileError('Choose a PDF file.');
      setReplacementFile(null);
      return;
    }
    if (file.size > MAX_PDF_SIZE) {
      setFileError('PDF must be 10 MB or smaller.');
      setReplacementFile(null);
      return;
    }
    setFileError('');
    setReplacementFile(file);
  };

  return (
    <AuthenticatedLayout title="Edit Thesis Metadata">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="flex items-center justify-between"><button className="flex items-center text-sm text-slate-500 hover:text-slate-800" onClick={() => navigate('my-projects')}><ArrowLeft className="mr-1 h-4 w-4" /> Back</button><div className="space-x-3"><Button variant="ghost" onClick={() => navigate('my-projects')}>Cancel</Button><Button onClick={() => void save()} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button></div></div>
        {message && <p className="text-sm text-red-600" role="alert">{message}</p>}
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-medium text-slate-900">Project information</h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Input label="Title" className="md:col-span-2" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            <Input label="Author" value={form.author} onChange={(event) => setForm({ ...form, author: event.target.value })} />
            <Input label="Year" type="number" value={form.year} onChange={(event) => setForm({ ...form, year: event.target.value })} />
            <Input label="Department" value={form.department} onChange={(event) => setForm({ ...form, department: event.target.value })} />
            <Input label="Faculty" value={form.faculty} onChange={(event) => setForm({ ...form, faculty: event.target.value })} />
            <Input label="Supervisor" value={form.supervisor} onChange={(event) => setForm({ ...form, supervisor: event.target.value })} />
            <Input label="Keywords" className="md:col-span-2" value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} />
          </div>
          <div className="mt-4 flex flex-col space-y-1.5"><label htmlFor="edit-thesis-abstract" className="text-sm font-medium text-slate-700">Abstract</label><textarea id="edit-thesis-abstract" className="h-36 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-[#00502F] focus:outline-none focus:ring-1 focus:ring-[#00502F]" value={form.abstract} onChange={(event) => setForm({ ...form, abstract: event.target.value })} /></div>
        </Card>
        {thesis.status === 'changes_requested' && <Card className="p-6"><div className="flex items-center gap-2"><FileUp className="h-5 w-5 text-[#00502F]" /><h3 className="text-lg font-medium text-slate-900">Replace submitted PDF</h3></div><p className="mt-1 text-sm text-slate-500">If the reviewer requested document changes, choose the revised PDF before resubmitting.</p><label htmlFor="replacement-pdf" className="mt-4 flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-4 hover:border-[#00502F]"><span className="truncate text-sm font-medium text-slate-700">{replacementFile ? `${replacementFile.name} · ${formatFileSize(replacementFile.size)}` : 'Choose a revised PDF (optional)'}</span><span className="shrink-0 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-[#00502F] shadow-sm">Browse</span></label><input id="replacement-pdf" type="file" accept="application/pdf,.pdf" className="sr-only" onChange={(event) => chooseReplacement(event.target.files?.[0])} />{fileError && <p className="mt-2 text-sm text-red-600" role="alert">{fileError}</p>}</Card>}
        <Card className="p-6"><h3 className="mb-2 text-lg font-medium text-slate-900">Next step</h3><p className="text-sm leading-6 text-slate-500">Saving keeps this submission in its current state. When your edits are ready, return to My Research and choose <strong>Submit for review</strong>.</p></Card>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen20EditThesis;
