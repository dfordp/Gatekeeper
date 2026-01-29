'use client';

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { attachmentSchema } from '@/lib/schemas/attachment';
import { z } from 'zod';

interface UseAttachmentsOptions {
  companyId: string;
  ticketId: string;
  enabled?: boolean;
}

export const useAttachments = ({
  companyId,
  ticketId,
  enabled = true,
}: UseAttachmentsOptions) => {
  return useQuery({
    queryKey: ['attachments', companyId, ticketId],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ATTACHMENTS.LIST(companyId, ticketId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          items: z.array(attachmentSchema),
        }),
      });

      return schema.parse(response.data).data.items;
    },
    enabled,
    staleTime: 1000 * 60 * 5,
  });
};