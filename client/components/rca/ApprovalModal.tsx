'use client';

import React, { useState } from 'react';
import { useApproveRCA, useRejectRCA } from '@/lib/hooks/useRCA';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';

interface ApprovalModalProps {
  isOpen: boolean;
  companyId: string;
  rcaId: string;
  mode: 'approve' | 'reject';
  onClose: () => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  isOpen,
  companyId,
  rcaId,
  mode,
  onClose,
}) => {
  const { mutate: approveRCA, isPending: isApproving } = useApproveRCA(
    companyId,
    rcaId
  );
  const { mutate: rejectRCA, isPending: isRejecting } = useRejectRCA(
    companyId,
    rcaId
  );

  const [feedback, setFeedback] = useState('');
  const [reason, setReason] = useState('');

  const handleApprove = (e: React.FormEvent) => {
    e.preventDefault();
    approveRCA(
      { feedback: feedback || undefined },
      { onSuccess: onClose }
    );
  };

  const handleReject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      alert('Please provide a reason for rejection');
      return;
    }
    rejectRCA({ reason }, { onSuccess: onClose });
  };

  return (
    <Modal
      isOpen={isOpen}
      title={mode === 'approve' ? 'Approve RCA' : 'Reject RCA'}
      onClose={onClose}
      size="md"
    >
      {mode === 'approve' ? (
        <form onSubmit={handleApprove} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Feedback (optional)
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Provide any feedback for the team..."
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-sm text-green-800">
              This RCA will be approved and embeddings will be generated.
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              type="submit"
              variant="primary"
              isLoading={isApproving}
            >
              Approve RCA
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <form onSubmit={handleReject} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Rejection Reason
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why are you rejecting this RCA?"
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>

          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-sm text-red-800">
              The RCA will be returned to draft status for further updates.
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              type="submit"
              variant="danger"
              isLoading={isRejecting}
            >
              Reject RCA
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
};