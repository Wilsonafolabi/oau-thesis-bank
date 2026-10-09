import React from 'react';
import { AuthenticatedLayout, Card } from '../components/shared';

const Screen44 = () => (
  <AuthenticatedLayout title="Content Moderation">
    <div className="mx-auto max-w-2xl">
      <Card className="p-8">
        <h2 className="text-xl font-bold text-slate-900">Content Moderation</h2>
        <p className="mt-2 leading-6 text-slate-600">Moderation queues and review actions require the Phase 2 admin API.</p>
        <p className="mt-4 text-sm text-slate-500">
          This screen is intentionally not fabricating records. The uploaded archive did not include the Phase 2 service that owns this data.
        </p>
      </Card>
    </div>
  </AuthenticatedLayout>
);

export default Screen44;
