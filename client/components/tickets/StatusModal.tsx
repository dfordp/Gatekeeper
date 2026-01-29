'use client';

import React, { useState } from 'react';
import { useChangeTicketStatus } from '@/lib/hooks/useChangeTicketStatus';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Select } from '@/components/common/Select';

interface StatusModalProps {
  isOpen: boolean;
  companyId: string;
  ticketId: string;
  currentStatus: string;
  onClose: () => void;
}

const STATUS_TRANSITIONS: Record<string, string[]> = {
  draft: ['open'],
  open: ['resolved', 'closed'],
  resolved: ['closed'],
  closed: [],
};

export const StatusModal: React.FC<StatusModalProps> = ({
  isOpen,
  companyId,
  ticketId,
  currentStatus,
  onClose,
}) => {
  const { mutate: changeStatus, isPending } = useChangeTicketStatus(
    companyId,
    ticketId
  );
  const [status, setStatus] = useState('');
  const [reason, setReason] = useState('');

  const allowedTransitions = STATUS_TRANSITIONS[currentStatus] || [];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!status) return;

    changeStatus(
      { new_status: status as 'draft' | 'open' | 'resolved' | 'closed', reason: reason || undefined },
      { onSuccess: onClose }
    );
  };

  return (
    <Modal isOpen={isOpen} title="Update Status" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Select
          label="New Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          options={allowedTransitions.map((s) => ({
            value: s,
            label: s.charAt(0).toUpperCase() + s.slice(1),
          }))}
          required
        />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Reason (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you updating the status?"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="flex gap-3">
          <Button type="submit" variant="primary" isLoading={isPending}>
            Update Status
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
};