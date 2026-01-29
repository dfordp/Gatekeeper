'use client';

import React, { useState } from 'react';
import { useAssignTicket } from '@/lib/hooks/useAssignTicket';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Select } from '@/components/common/Select';

interface AssignModalProps {
  isOpen: boolean;
  companyId: string;
  ticketId: string;
  onClose: () => void;
}

// Mock engineers - in real app, fetch from backend
const MOCK_ENGINEERS = [
  { value: '123e4567-e89b-12d3-a456-426614174000', label: 'John Doe' },
  { value: '123e4567-e89b-12d3-a456-426614174001', label: 'Jane Smith' },
  { value: '123e4567-e89b-12d3-a456-426614174002', label: 'Bob Johnson' },
];

export const AssignModal: React.FC<AssignModalProps> = ({
  isOpen,
  companyId,
  ticketId,
  onClose,
}) => {
  const { mutate: assignTicket, isPending } = useAssignTicket(
    companyId,
    ticketId
  );
  const [engineer_id, setEngineerId] = useState('');
  const [reason, setReason] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!engineer_id) return;

    assignTicket(
      { engineer_id, reason: reason || undefined },
      { onSuccess: onClose }
    );
  };

  return (
    <Modal isOpen={isOpen} title="Assign Ticket" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Select
          label="Engineer"
          value={engineer_id}
          onChange={(e) => setEngineerId(e.target.value)}
          options={MOCK_ENGINEERS}
          required
        />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Reason (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you assigning this ticket?"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="flex gap-3">
          <Button type="submit" variant="primary" isLoading={isPending}>
            Assign
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
};