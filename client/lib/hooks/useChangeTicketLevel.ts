'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import {
  ChangeTicketLevelRequest,
  ticketSchema,
} from '@/lib/schemas/ticket';
import { z } from 'zod';
import toast from 'react-hot-toast';

export const useChangeTicketLevel = (
  companyId: string,
  ticketId: string
) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ChangeTicketLevelRequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.TICKETS.CHANGE_LEVEL(companyId, ticketId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: ticketSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['ticket', companyId, ticketId],
      });
      queryClient.invalidateQueries({
        queryKey: ['tickets', companyId],
      });
      toast.success('Ticket level updated');
    },
    onError: (error: Error) => {
      const apiError = error as AxiosError<{ detail: string }>;
      toast.error(
        apiError.response?.data?.detail || 'Failed to update ticket level'
      );
    },
  });
};