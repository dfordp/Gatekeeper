'use client';

import React, { useState } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useRCA } from '@/lib/hooks/useRCA';
import { RCAForm } from '@/components/rca/RCAForm';
import { RCATimeline } from '@/components/rca/RCATimeline';
import { ApprovalModal } from '@/components/rca/ApprovalModal';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';

export default function RCAPage({
  params,
}: {
  params: { ticket_id: string };
}) {
  const { user } = useAuth();
  const { data: rca, isLoading } = useRCA({
    companyId: user?.company_id || '',
    ticketId: params.ticket_id,
    enabled: !!user?.company_id,
  });

  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [approvalMode, setApprovalMode] = useState<'approve' | 'reject'>(
    'approve'
  );

  const isAdmin =
    user?.role === 'company_admin' || user?.role === 'platform_admin';

  if (isLoading) return <Loading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">Root Cause Analysis</h1>
        <p className="text-gray-600 mt-2">
          Document the root cause and corrective actions
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form / View */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow p-6">
            {!rca ? (
              <div>
                <h2 className="text-lg font-semibold text-gray-800 mb-4">
                  Create RCA
                </h2>
                <RCAForm
                  companyId={user?.company_id || ''}
                  ticketId={params.ticket_id}
                />
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-800">
                    RCA Details
                  </h2>
                  <div className="text-sm">
                    <span className="px-3 py-1 rounded-full font-medium capitalize
                      {rca.status === 'draft' && ' bg-gray-100 text-gray-800'}
                      {rca.status === 'pending_approval' && ' bg-yellow-100 text-yellow-800'}
                      {rca.status === 'approved' && ' bg-green-100 text-green-800'}
                      {rca.status === 'deprecated' && ' bg-gray-100 text-gray-800'}
                    ">
                      {rca.status.replace('_', ' ')}
                    </span>
                  </div>
                </div>

                <RCAForm
                  companyId={user?.company_id || ''}
                  ticketId={params.ticket_id}
                />

                {/* Admin Actions */}
                {isAdmin && rca.status === 'pending_approval' && (
                  <div className="mt-6 pt-6 border-t border-gray-200 flex gap-3">
                    <Button
                      variant="primary"
                      onClick={() => {
                        setApprovalMode('approve');
                        setShowApprovalModal(true);
                      }}
                    >
                      Approve
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => {
                        setApprovalMode('reject');
                        setShowApprovalModal(true);
                      }}
                    >
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Timeline */}
        {rca && (
          <div>
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-4">
                Approval Timeline
              </h2>
              <RCATimeline
                companyId={user?.company_id || ''}
                rcaId={rca.id}
              />
            </div>
          </div>
        )}
      </div>

      {/* Approval Modal */}
      {rca && (
        <ApprovalModal
          isOpen={showApprovalModal}
          companyId={user?.company_id || ''}
          rcaId={rca.id}
          mode={approvalMode}
          onClose={() => setShowApprovalModal(false)}
        />
      )}
    </div>
  );
}