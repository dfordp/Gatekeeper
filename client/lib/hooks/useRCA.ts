'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import {
  rcaSchema,
  CreateRCARequest,
  UpdateRCARequest,
  SubmitRCARequest,
  ApproveRCARequest,
  RejectRCARequest,
} from '@/lib/schemas/rca';
import { z } from 'zod';
import toast from 'react-hot-toast';

interface ErrorResponse {
  detail?: string;
}

interface UseRCAOptions {
  companyId: string;
  ticketId: string;
  enabled?: boolean;
}

export const useRCA = ({
  companyId,
  ticketId,
  enabled = true,
}: UseRCAOptions) => {
  return useQuery({
    queryKey: ['rca', companyId, ticketId],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.RCA.GET(companyId, ticketId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    enabled,
    staleTime: 1000 * 60 * 5,
  });
};

export const useCreateRCA = (companyId: string, ticketId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateRCARequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.RCA.CREATE(companyId, ticketId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['rca', companyId, ticketId],
      });
      toast.success('RCA created');
    },
    onError: (error: AxiosError) => {
      toast.error((error.response?.data as ErrorResponse)?.detail || 'Failed to create RCA');
    },
  });
};

export const useUpdateRCA = (companyId: string, rcaId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: UpdateRCARequest) => {
      const response = await apiClient.put(
        API_ENDPOINTS.RCA.UPDATE(companyId, rcaId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['rca', companyId],
      });
      toast.success('RCA updated');
    },
    onError: (error: AxiosError) => {
      toast.error((error.response?.data as ErrorResponse)?.detail || 'Failed to update RCA');
    },
  });
};

export const useSubmitRCA = (companyId: string, rcaId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: SubmitRCARequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.RCA.SUBMIT(companyId, rcaId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['rca', companyId],
      });
      toast.success('RCA submitted for approval');
    },
    onError: (error: AxiosError) => {
      toast.error((error.response?.data as ErrorResponse)?.detail || 'Failed to submit RCA');
    },
  });
};

export const useApproveRCA = (companyId: string, rcaId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ApproveRCARequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.RCA.APPROVE(companyId, rcaId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['rca', companyId],
      });
      toast.success('RCA approved');
    },
    onError: (error: AxiosError) => {
      toast.error((error.response?.data as ErrorResponse)?.detail || 'Failed to approve RCA');
    },
  });
};

export const useRejectRCA = (companyId: string, rcaId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: RejectRCARequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.RCA.REJECT(companyId, rcaId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: rcaSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['rca', companyId],
      });
      toast.success('RCA rejected');
    },
    onError: (error: AxiosError) => {
      toast.error((error.response?.data as ErrorResponse)?.detail || 'Failed to reject RCA');
    },
  });
};