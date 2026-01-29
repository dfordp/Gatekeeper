'use client';

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { ticketSchema } from '@/lib/schemas/ticket';
import { paginatedResponseSchema } from '@/lib/schemas/common';
import { z } from 'zod';

interface UseTicketsOptions {
  companyId: string;
  page?: number;
  limit?: number;
  status?: string;
  level?: string;
  category?: string;
  assignee?: string;
  search?: string;
}

export const useTickets = ({
  companyId,
  page = 1,
  limit = 20,
  status,
  level,
  category,
  assignee,
  search,
}: UseTicketsOptions) => {
  return useQuery({
    queryKey: [
      'tickets',
      companyId,
      page,
      limit,
      status,
      level,
      category,
      assignee,
      search,
    ],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('limit', limit.toString());
      if (status) params.append('status', status);
      if (level) params.append('level', level);
      if (category) params.append('category', category);
      if (assignee) params.append('assignee', assignee);
      if (search) params.append('search', search);

      const response = await apiClient.get(
        `${API_ENDPOINTS.TICKETS.LIST(companyId)}?${params.toString()}`
      );

      const schema = z.object({
        success: z.boolean(),
        data: paginatedResponseSchema(ticketSchema),
      });

      return schema.parse(response.data).data;
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
};