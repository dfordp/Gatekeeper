'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useCreateTicket } from '@/lib/hooks/useCreateTicket';
import { createTicketRequestSchema } from '@/lib/schemas/ticket';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';

interface TicketFormProps {
  companyId: string;
  onSuccess?: () => void;
}

export const TicketForm: React.FC<TicketFormProps> = ({
  companyId,
  onSuccess,
}) => {
  const router = useRouter();
  const { mutate: createTicket, isPending } = useCreateTicket(companyId);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    category: 'other',
  });

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: '' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const result = createTicketRequestSchema.safeParse(formData);
    if (!result.success) {
      const newErrors: Record<string, string> = {};
      result.error.errors.forEach((err) => {
        if (err.path[0]) {
          newErrors[err.path[0]] = err.message;
        }
      });
      setErrors(newErrors);
      return;
    }

    createTicket(result.data, {
      onSuccess: (ticket) => {
        onSuccess?.();
        router.push(`/dashboard/tickets/${ticket.id}`);
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Input
        label="Title"
        name="title"
        placeholder="Brief description of the issue"
        value={formData.title}
        onChange={handleChange}
        error={errors.title}
        required
      />

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Description
        </label>
        <textarea
          name="description"
          placeholder="Detailed description of the issue"
          value={formData.description}
          onChange={handleChange}
          rows={5}
          className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.description ? 'border-red-500' : 'border-gray-300'
          }`}
          required
        />
        {errors.description && (
          <p className="text-red-500 text-sm mt-1">{errors.description}</p>
        )}
      </div>

      <Select
        label="Category"
        name="category"
        value={formData.category}
        onChange={handleChange}
        options={[
          { value: 'bug', label: 'Bug' },
          { value: 'feature_request', label: 'Feature Request' },
          { value: 'documentation', label: 'Documentation' },
          { value: 'support', label: 'Support' },
          { value: 'other', label: 'Other' },
        ]}
      />

      <div className="flex gap-3">
        <Button type="submit" variant="primary" isLoading={isPending}>
          Create Ticket
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => router.back()}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
};