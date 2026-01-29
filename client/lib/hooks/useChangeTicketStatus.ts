'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import {
  UpdateTicketStatusRequest,
  ticketSchema,
} from '@/lib/schemas/ticket';
import { z } from 'zod';
import toast from 'react-hot-toast';

export const useChangeTicketStatus = (
  companyId: string,
  ticketId: string
) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: UpdateTicketStatusRequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.TICKETS.UPDATE_STATUS(companyId, ticketId),
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
      toast.success('Ticket status updated');
    },
    onError: (error: Error) => {
      const apiError = error as { response?: { data?: { detail?: string } } };
      toast.error(
        apiError.response?.data?.detail || 'Failed to update ticket status'
      );
    },
  });
};