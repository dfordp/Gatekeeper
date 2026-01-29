'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { CommentRequest } from '@/lib/schemas/ticket';
import { z } from 'zod';
import toast from 'react-hot-toast';
import { AxiosError } from 'axios';

interface ErrorResponse {
  detail?: string;
}

export const useAddComment = (companyId: string, ticketId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CommentRequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.TICKETS.ADD_COMMENT(companyId, ticketId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({ event_id: z.string() }),
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      // Invalidate both ticket detail and events
      queryClient.invalidateQueries({
        queryKey: ['ticket', companyId, ticketId],
      });
      queryClient.invalidateQueries({
        queryKey: ['ticketEvents', companyId, ticketId],
      });
      toast.success('Comment added');
    },
    onError: (error: AxiosError<ErrorResponse>) => {
      toast.error(error.response?.data?.detail || 'Failed to add comment');
    },
  });
};