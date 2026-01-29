'use client';

import React, { useState } from 'react';
import { useChangeTicketLevel } from '@/lib/hooks/useChangeTicketLevel';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Select } from '@/components/common/Select';

interface LevelModalProps {
  isOpen: boolean;
  companyId: string;
  ticketId: string;
  currentLevel: string;
  onClose: () => void;
}

export const LevelModal: React.FC<LevelModalProps> = ({
  isOpen,
  companyId,
  ticketId,
  currentLevel,
  onClose,
}) => {
  const { mutate: changeLevel, isPending } = useChangeTicketLevel(
    companyId,
    ticketId
  );
  const [level, setLevel] = useState(currentLevel);
  const [reason, setReason] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!level) return;

    changeLevel(
      { new_level: level as 'P0' | 'P1' | 'P2' | 'P3', reason: reason || undefined },
      { onSuccess: onClose }
    );
  };

  return (
    <Modal isOpen={isOpen} title="Change Severity Level" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Select
          label="Level"
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          options={[
            { value: 'P0', label: 'P0 - Critical' },
            { value: 'P1', label: 'P1 - High' },
            { value: 'P2', label: 'P2 - Medium' },
            { value: 'P3', label: 'P3 - Low' },
          ]}
          required
        />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Reason (optional)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you changing the severity level?"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="flex gap-3">
          <Button type="submit" variant="primary" isLoading={isPending}>
            Update Level
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
};