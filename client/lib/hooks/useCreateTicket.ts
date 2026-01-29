'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { CreateTicketRequest, ticketSchema } from '@/lib/schemas/ticket';
import { z } from 'zod';
import toast from 'react-hot-toast';

export const useCreateTicket = (companyId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateTicketRequest) => {
      const response = await apiClient.post(
        API_ENDPOINTS.TICKETS.CREATE(companyId),
        data
      );

      const schema = z.object({
        success: z.boolean(),
        data: ticketSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: (newTicket) => {
      // Invalidate tickets list
      queryClient.invalidateQueries({
        queryKey: ['tickets', companyId],
      });

      toast.success(`Ticket ${newTicket.ticket_number} created`);
    },
    onError: (error: Error) => {
      const message =
        (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to create ticket';
      toast.error(message);
    },
  });
};