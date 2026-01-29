'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { attachmentSchema } from '@/lib/schemas/attachment';
import { z } from 'zod';
import toast from 'react-hot-toast';
import { AxiosError } from 'axios';

export const useUploadAttachment = (
  companyId: string,
  ticketId: string
) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await apiClient.post(
        API_ENDPOINTS.ATTACHMENTS.UPLOAD(companyId, ticketId),
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      const schema = z.object({
        success: z.boolean(),
        data: attachmentSchema,
      });

      return schema.parse(response.data).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['attachments', companyId, ticketId],
      });
      toast.success('File uploaded successfully');
    },
    onError: (error: Error) => {
      const apiError = error as AxiosError<{ detail: string }>;
      toast.error(
        apiError.response?.data?.detail || 'Failed to upload file'
      );
    },
  });
};