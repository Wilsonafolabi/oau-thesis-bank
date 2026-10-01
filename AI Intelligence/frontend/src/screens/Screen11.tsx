import React, { useState, useEffect } from 'react';
import { AuthenticatedLayout, useAppRouter } from '../components/shared';

const Screen11PdfReader = () => {
  const { navigate } = useAppRouter();
  const [thesis, setThesis] = useState<any>(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const searchId = new URLSearchParams(window.location.search).get('thesisId');
  const pathId = window.location.pathname.split('/').pop();
  const id = pathId !== 'reader' ? pathId : searchId;

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access') || localStorage.getItem('token');
        const headers: any = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        // 1. Get Thesis Details
        const res = await fetch(`http://localhost:8000/api/theses/${id}/`, { headers });
        if (!res.ok) throw new Error('Failed to load thesis details.');
        const data = await res.json();
        setThesis(data);

        // 2. If there is a PDF, fetch it as a Blob using the token
        if (data.file_url) {
          const pdfRes = await fetch(`http://localhost:8000${data.file_url}`, { headers });
          if (!pdfRes.ok) throw new Error('Failed to load PDF file.');
          
          const blob = await pdfRes.blob();
          const objectUrl = URL.createObjectURL(blob);
          setPdfBlobUrl(objectUrl);
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (id) fetchData();

    // Cleanup blob URL when component unmounts
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [id]);

  if (loading) return <AuthenticatedLayout title="Loading..."><div className="p-8 text-center">Loading PDF securely...</div></AuthenticatedLayout>;
  if (error) return <AuthenticatedLayout title="Error"><div className="p-8 text-center text-red-600">{error}</div></AuthenticatedLayout>;
  if (!thesis) return <AuthenticatedLayout title="Not Found"><div className="p-8 text-center">Thesis not found.</div></AuthenticatedLayout>;

  if (!pdfBlobUrl) {
    return (
      <AuthenticatedLayout title="PDF Reader">
        <div className="flex flex-col items-center justify-center p-12 text-center border border-yellow-200 bg-yellow-50 rounded-lg max-w-2xl mx-auto mt-10">
          <div className="text-4xl mb-4">??</div>
          <h3 className="text-xl font-bold text-yellow-900 mb-2">No PDF Available</h3>
          <p className="text-yellow-700">This thesis record does not currently contain a downloadable PDF file.</p>
        </div>
      </AuthenticatedLayout>
    );
  }

  return (
    <AuthenticatedLayout title={`Reading: ${thesis.title}`}>
      <div className="h-[85vh] w-full bg-gray-100 rounded-lg overflow-hidden border border-gray-300">
        <iframe 
          src={pdfBlobUrl} 
          className="w-full h-full"
          title="Thesis PDF Viewer"
        />
      </div>
      <div className="mt-4 flex gap-4">
        <button onClick={() => navigate(-1)} className="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300">
          ? Back to Thesis
        </button>
        <a href={pdfBlobUrl} download={`${thesis.title}.pdf`} className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">
          Download PDF
        </a>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen11PdfReader;