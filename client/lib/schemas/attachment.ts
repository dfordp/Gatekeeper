import { z } from 'zod';

export const attachmentSchema = z.object({
  id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  company_id: z.string().uuid(),
  filename: z.string(),
  file_path: z.string(),
  file_size: z.number(),
  mime_type: z.string(),
  uploaded_by: z.string().uuid(),
  uploader_name: z.string(),
  is_active: z.boolean(),
  deprecated_at: z.string().nullable(),
  deprecation_reason: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Attachment = z.infer<typeof attachmentSchema>;

export const deprecateAttachmentRequestSchema = z.object({
  reason: z
    .string()
    .min(1, 'Deprecation reason is required')
    .max(500),
});

export type DeprecateAttachmentRequest = z.infer<
  typeof deprecateAttachmentRequestSchema
>;