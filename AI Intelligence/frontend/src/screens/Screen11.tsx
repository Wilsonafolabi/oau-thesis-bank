import { useEffect, useState } from 'react';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { EmptyState, ErrorState, LoadingState } from '../components/AsyncState';
import { Button, PublicOrAuthenticatedLayout, useAppRouter } from '../components/shared';
import { useApi } from '../hooks/useApi';
import { apiErrorMessage, downloadThesis, getThesis } from '../lib/api';
import AIInsightsDashboard from '../components/AIInsightsDashboard'; // <-- AI Component Added

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
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Header Section */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
          <div className="min-w-0">
            <Button variant="ghost" className="mb-2" onClick={() => navigate('thesis-detail', { thesisId })}>
              <ArrowLeft className="mr-2 h-4 w-4" /> Thesis details
            </Button>
            <h2 className="truncate text-xl font-bold text-slate-900">{title}</h2>
            {thesis?.author && <p className="mt-1 text-sm text-slate-500">By {thesis.author}</p>}
          </div>
          {pdfUrl && (
            <Button variant="secondary" onClick={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}>
              <ExternalLink className="mr-2 h-4 w-4" /> Open in new tab
            </Button>
          )}
        </div>

        {/* PDF Viewer Section */}
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
          <div className="overflow-hidden rounded-lg border border-slate-300 bg-slate-100 shadow-sm">
            <iframe
              title={`PDF reader: ${title}`}
              src={pdfUrl}
              className="block h-[calc(100vh-16rem)] min-h-[500px] w-full"
            />
          </div>
        )}

        {/* ========================================== */}
        {/* AI INSIGHTS DASHBOARD (Section 7.7, 7.8)  */}
        {/* ========================================== */}
        <div className="mt-10 border-t border-slate-200 pt-8">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-bold text-slate-900">AI Research Insights</h3>
              <p className="text-sm text-slate-500">Powered by the OAU Thesis Bank AI Intelligence Service</p>
            </div>
          </div>
          
          {/* Note: In production, replace "student_1" with the actual logged-in user's ID from your auth context */}
          <AIInsightsDashboard userId="student_1" />
        </div>

      </div>
      {/* Add some bottom padding so the dashboard doesn't hit the screen edge */}
      <div className="h-12"></div>
    </PublicOrAuthenticatedLayout>
  );
};

export default Screen11PdfReader;