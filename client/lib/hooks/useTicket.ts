'use client';

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { ticketSchema } from '@/lib/schemas/ticket';
import { z } from 'zod';

interface UseTicketOptions {
  companyId: string;
  ticketId: string;
  enabled?: boolean;
}

export const useTicket = ({
  companyId,
  ticketId,
  enabled = true,
}: UseTicketOptions) => {
  return useQuery({
    queryKey: ['ticket', companyId, ticketId],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.TICKETS.DETAIL(companyId, ticketId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: ticketSchema,
      });

      return schema.parse(response.data).data;
    },
    enabled,
    staleTime: 1000 * 60 * 5,
  });
};