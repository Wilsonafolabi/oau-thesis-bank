import React from 'react';
import { AuthenticatedLayout, Card } from '../components/shared';

const Screen30 = () => (
  <AuthenticatedLayout title="Researcher Profile">
    <div className="mx-auto max-w-2xl">
      <Card className="p-8">
        <h2 className="text-xl font-bold text-slate-900">Researcher Profile</h2>
        <p className="mt-2 leading-6 text-slate-600">The profile data source is the Phase 2 researcher profile API.</p>
        <p className="mt-4 text-sm text-slate-500">
          This screen is intentionally not fabricating records. The uploaded archive did not include the Phase 2 service that owns this data.
        </p>
      </Card>
    </div>
  </AuthenticatedLayout>
);

export default Screen30;
