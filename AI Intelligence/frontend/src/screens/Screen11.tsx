import { useEffect, useState } from 'react';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { Button, PublicOrAuthenticatedLayout, useAppRouter } from '../components/shared';
import { useApi } from '../hooks/useApi';
import { apiErrorMessage, downloadThesis, getThesis } from '../lib/api';

const Screen11PdfReader = () => {
  const { currentScreen, navigate } = useAppRouter();
  const thesisId = Number(currentScreen.params?.thesisId || currentScreen.params?.id);
  const hasThesisId = Number.isSafeInteger(thesisId) && thesisId > 0;
  const { data: thesis, loading: thesisLoading, error: thesisError, refetch } = useApi(
    hasThesisId ? () => getThesis(thesisId) : null,
    [thesisId],
    hasThesisId,
  );
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(hasThesisId);
  const [pdfError, setPdfError] = useState<unknown>(null);
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    if (!hasThesisId) return undefined;

    let cancelled = false;
    let objectUrl: string | null = null;
    setPdfUrl(null);
    setPdfLoading(true);
    setPdfError(null);

    downloadThesis(thesisId)
      .then((blob) => {
        if (!blob.size) throw new Error('The thesis PDF is empty.');
        const pdfBlob = new Blob([blob], { type: 'application/pdf' });
        const nextUrl = URL.createObjectURL(pdfBlob);
        if (cancelled) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        objectUrl = nextUrl;
        setPdfUrl(nextUrl);
      })
      .catch((error: unknown) => {
        if (!cancelled) setPdfError(error);
      })
      .finally(() => {
        if (!cancelled) setPdfLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [hasThesisId, thesisId, retryVersion]);

  if (!hasThesisId) {
    return (
      <PublicOrAuthenticatedLayout title="PDF Reader">
        <EmptyState title="No thesis selected" description="Open a thesis from the repository to read its PDF." />
      </PublicOrAuthenticatedLayout>
    );
  }

  const title = thesis?.title || 'Thesis PDF';
  const retryPdf = () => setRetryVersion((version) => version + 1);

  return (
    <PublicOrAuthenticatedLayout title="PDF Reader">
      <div className="mx-auto max-w-7xl">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <Button variant="ghost" className="mb-2" onClick={() => navigate('thesis-detail', { thesisId })}>
              <ArrowLeft className="mr-2 h-4 w-4" /> Thesis details
            </Button>
            <h2 className="truncate text-lg font-semibold text-slate-900">{title}</h2>
            {thesis?.author && <p className="mt-1 text-sm text-slate-500">{thesis.author}</p>}
          </div>
          {pdfUrl && (
            <Button variant="secondary" onClick={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}>
              <ExternalLink className="mr-2 h-4 w-4" /> Open in new tab
            </Button>
          )}
        </div>

        {thesisError && !pdfUrl && !pdfError && (
          <ErrorState message={apiErrorMessage(thesisError, 'Unable to load this thesis.')} onRetry={() => void refetch()} />
        )}
        {pdfError && (
          <ErrorState
            message={apiErrorMessage(pdfError, 'Unable to load this PDF. Check that you have access and the thesis includes a PDF.')}
            onRetry={retryPdf}
          />
        )}
        {!pdfError && (pdfLoading || (thesisLoading && !thesis)) && <LoadingState label="Loading thesis PDF…" />}
        {!pdfLoading && !pdfError && pdfUrl && (
          <div className="overflow-hidden rounded-md border border-slate-300 bg-slate-200">
            <iframe
              title={`PDF reader: ${title}`}
              src={pdfUrl}
              className="block h-[calc(100vh-13rem)] min-h-[420px] w-full"
            />
          </div>
        )}
      </div>
    </PublicOrAuthenticatedLayout>
  );
};

export default Screen11PdfReader;