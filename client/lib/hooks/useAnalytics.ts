'use client';

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { z } from 'zod';

export const useDuplicateTickets = (companyId: string) => {
  return useQuery({
    queryKey: ['analytics', companyId, 'duplicates'],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ANALYTICS.DUPLICATES(companyId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          groups: z.array(
            z.object({
              ticket_ids: z.array(z.string()),
              similarity_score: z.number(),
            })
          ),
        }),
      });

      return schema.parse(response.data).data;
    },
    staleTime: 1000 * 60 * 10,
  });
};

export const useTicketCategories = (companyId: string) => {
  return useQuery({
    queryKey: ['analytics', companyId, 'categories'],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ANALYTICS.CATEGORIES(companyId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          categories: z.record(z.number()),
        }),
      });

      return schema.parse(response.data).data;
    },
    staleTime: 1000 * 60 * 10,
  });
};

export const useEmbeddingMetrics = (companyId: string) => {
  return useQuery({
    queryKey: ['analytics', companyId, 'embeddings'],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ANALYTICS.EMBEDDINGS(companyId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          active_count: z.number(),
          deprecated_count: z.number(),
        }),
      });

      return schema.parse(response.data).data;
    },
    staleTime: 1000 * 60 * 10,
  });
};

export const useApprovalMetrics = (companyId: string) => {
  return useQuery({
    queryKey: ['analytics', companyId, 'approvals'],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ANALYTICS.APPROVALS(companyId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          avg_turnaround_hours: z.number(),
          total_approved: z.number(),
          total_rejected: z.number(),
          approval_rate: z.number(),
        }),
      });

      return schema.parse(response.data).data;
    },
    staleTime: 1000 * 60 * 10,
  });
};