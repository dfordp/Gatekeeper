'use client';

import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import toast from 'react-hot-toast';

interface DeprecateModalProps {
  isOpen: boolean;
  companyId: string;
  attachmentId: string;
  onClose: () => void;
}

export const DeprecateModal: React.FC<DeprecateModalProps> = ({
  isOpen,
  companyId,
  attachmentId,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const { mutate: deprecateAttachment, isPending } = useMutation({
    mutationFn: async () => {
      if (!reason.trim()) {
        setError('Please provide a reason for deprecation');
        throw new Error('Reason required');
      }

      const response = await apiClient.post(
        API_ENDPOINTS.ATTACHMENTS.DEPRECATE(companyId, attachmentId),
        { reason }
      );

      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['attachments', companyId],
      });
      toast.success('File deprecated successfully');
      onClose();
    },
    onError: (err: Error) => {
      const apiError = err as { response?: { data?: { detail?: string } } };
      toast.error(
        apiError.response?.data?.detail || 'Failed to deprecate file'
      );
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    deprecateAttachment();
  };

  return (
    <Modal
      isOpen={isOpen}
      title="Deprecate File"
      onClose={onClose}
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Reason for Deprecation
          </label>
          <textarea
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setError('');
            }}
            placeholder="Why are you deprecating this file?"
            rows={4}
            className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              error ? 'border-red-500' : 'border-gray-300'
            }`}
            required
          />
          {error && <p className="text-red-500 text-sm mt-1">{error}</p>}
        </div>

        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-sm text-red-800">
            ⚠️ This file will be marked as deprecated and hidden from view.
            It will not be deleted permanently.
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            type="submit"
            variant="danger"
            isLoading={isPending}
          >
            Deprecate File
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
};