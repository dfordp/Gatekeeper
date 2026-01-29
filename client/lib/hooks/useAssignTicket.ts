'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { AssignTicketRequest, ticketSchema } from '@/lib/schemas/ticket';
import { z } from 'zod';
import toast from 'react-hot-toast';

export const useAssignTicket = (companyId: string, ticketId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: AssignTicketRequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.TICKETS.ASSIGN(companyId, ticketId),
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
      toast.success('Ticket assigned successfully');
    },
    onError: (error: Error) => {
      const apiError = error as { response?: { data?: { detail?: string } } };
      toast.error(
        apiError.response?.data?.detail || 'Failed to assign ticket'
      );
    },
  });
};