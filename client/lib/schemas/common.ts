import { z } from 'zod';

export const apiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema,
    meta: z.record(z.any()).optional(),
  });

export const paginatedResponseSchema = <T extends z.ZodTypeAny>(
  itemSchema: T
) =>
  z.object({
    items: z.array(itemSchema),
    total: z.number(),
    page: z.number(),
    limit: z.number(),
    pages: z.number(),
  });

export const badgeSchema = z.enum(['draft', 'open', 'resolved', 'closed']);
export type BadgeType = z.infer<typeof badgeSchema>;