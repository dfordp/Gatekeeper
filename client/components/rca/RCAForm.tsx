'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  useRCA,
  useCreateRCA,
  useUpdateRCA,
  useSubmitRCA,
} from '@/lib/hooks/useRCA';
import {
  createRCARequestSchema,
  RCA,
} from '@/lib/schemas/rca';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';

interface RCAFormProps {
  companyId: string;
  ticketId: string;
  onSuccess?: () => void;
}

export const RCAForm: React.FC<RCAFormProps> = ({
  companyId,
  ticketId,
  onSuccess,
}) => {
  const router = useRouter();
  const { data: existingRCA, isLoading: isLoadingRCA } = useRCA({
    companyId,
    ticketId,
    enabled: true,
  });

  const { mutate: createRCA, isPending: isCreating } = useCreateRCA(
    companyId,
    ticketId
  );
  const { mutate: updateRCA, isPending: isUpdating } = useUpdateRCA(
    companyId,
    existingRCA?.id || ''
  );
  const { mutate: submitRCA, isPending: isSubmitting } = useSubmitRCA(
    companyId,
    existingRCA?.id || ''
  );

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formData, setFormData] = useState({
    root_cause: '',
    corrective_actions: '',
    prevention_measures: '',
  });

  // Populate form if RCA exists
  useEffect(() => {
    const process = async () => {
        if (existingRCA && existingRCA.status === 'draft') {
        setFormData({
            root_cause: existingRCA.root_cause,
            corrective_actions: existingRCA.corrective_actions,
            prevention_measures: existingRCA.prevention_measures,
        });
        }
    }

    process();
  }, [existingRCA]);

  const handleChange = (
    e: React.ChangeEvent<HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: '' }));
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();

    const result = createRCARequestSchema.safeParse(formData);
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

    if (existingRCA) {
      updateRCA(result.data, { onSuccess: onSuccess });
    } else {
      createRCA(result.data, { onSuccess: onSuccess });
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const result = createRCARequestSchema.safeParse(formData);
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

    if (!existingRCA) {
      createRCA(result.data, {
        onSuccess: (newRCA) => {
          submitRCA({}, { onSuccess: onSuccess });
        },
      });
    } else {
      submitRCA({}, { onSuccess: onSuccess });
    }
  };

  if (isLoadingRCA) return <Loading />;

  // Read-only view if approved
  if (existingRCA && existingRCA.status !== 'draft') {
    return (
      <div className="space-y-6">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-blue-800 font-medium">
            This RCA is {existingRCA.status.replace('_', ' ')} and cannot be
            edited.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Root Cause
            </label>
            <div className="p-4 bg-gray-50 rounded-lg text-gray-700 whitespace-pre-wrap">
              {existingRCA.root_cause}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Corrective Actions
            </label>
            <div className="p-4 bg-gray-50 rounded-lg text-gray-700 whitespace-pre-wrap">
              {existingRCA.corrective_actions}
            </div>
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Prevention Measures
            </label>
            <div className="p-4 bg-gray-50 rounded-lg text-gray-700 whitespace-pre-wrap">
              {existingRCA.prevention_measures}
            </div>
          </div>
        </div>

        {existingRCA.status === 'pending_approval' && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-yellow-800 font-medium">
              ⏳ Awaiting approval from admin
            </p>
          </div>
        )}

        {existingRCA.status === 'approved' && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-800 font-medium">
              ✓ Approved on {new Date(existingRCA.approved_at!).toLocaleDateString()}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Root Cause Analysis
        </label>
        <textarea
          name="root_cause"
          placeholder="What was the root cause of this issue?"
          value={formData.root_cause}
          onChange={handleChange}
          rows={5}
          className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.root_cause ? 'border-red-500' : 'border-gray-300'
          }`}
          required
        />
        {errors.root_cause && (
          <p className="text-red-500 text-sm mt-1">{errors.root_cause}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Corrective Actions
        </label>
        <textarea
          name="corrective_actions"
          placeholder="What actions were taken to resolve the issue?"
          value={formData.corrective_actions}
          onChange={handleChange}
          rows={5}
          className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.corrective_actions ? 'border-red-500' : 'border-gray-300'
          }`}
          required
        />
        {errors.corrective_actions && (
          <p className="text-red-500 text-sm mt-1">{errors.corrective_actions}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Prevention Measures
        </label>
        <textarea
          name="prevention_measures"
          placeholder="How will we prevent this issue in the future?"
          value={formData.prevention_measures}
          onChange={handleChange}
          rows={5}
          className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.prevention_measures ? 'border-red-500' : 'border-gray-300'
          }`}
          required
        />
        {errors.prevention_measures && (
          <p className="text-red-500 text-sm mt-1">{errors.prevention_measures}</p>
        )}
      </div>

      <div className="flex gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={handleSave}
          isLoading={isCreating || isUpdating}
        >
          Save Draft
        </Button>
        <Button
          type="button"
          variant="primary"
          onClick={handleSubmit}
          isLoading={isSubmitting}
        >
          Submit for Approval
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