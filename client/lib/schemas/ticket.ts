import { z } from 'zod';

export const ticketStatusSchema = z.enum(['draft', 'open', 'resolved', 'closed']);
export type TicketStatus = z.infer<typeof ticketStatusSchema>;

export const ticketLevelSchema = z.enum(['P0', 'P1', 'P2', 'P3']);
export type TicketLevel = z.infer<typeof ticketLevelSchema>;

export const ticketCategorySchema = z.enum([
  'bug',
  'feature_request',
  'documentation',
  'support',
  'other',
]);
export type TicketCategory = z.infer<typeof ticketCategorySchema>;

export const ticketSchema = z.object({
  id: z.string().uuid(),
  ticket_number: z.string(),
  company_id: z.string().uuid(),
  requester_id: z.string().uuid(),
  assigned_to: z.string().uuid().nullable(),
  title: z.string(),
  description: z.string(),
  status: ticketStatusSchema,
  level: ticketLevelSchema,
  category: ticketCategorySchema,
  created_at: z.string(),
  updated_at: z.string(),
});

export type Ticket = z.infer<typeof ticketSchema>;

export const createTicketRequestSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255),
  description: z.string().min(1, 'Description is required').max(5000),
  category: ticketCategorySchema.default('other'),
});

export type CreateTicketRequest = z.infer<typeof createTicketRequestSchema>;

export const updateTicketStatusRequestSchema = z.object({
  new_status: ticketStatusSchema,
  reason: z.string().optional(),
});

export type UpdateTicketStatusRequest = z.infer<
  typeof updateTicketStatusRequestSchema
>;

export const assignTicketRequestSchema = z.object({
  engineer_id: z.string().uuid(),
  reason: z.string().optional(),
});

export type AssignTicketRequest = z.infer<typeof assignTicketRequestSchema>;

export const changeTicketLevelRequestSchema = z.object({
  new_level: ticketLevelSchema,
  reason: z.string().optional(),
});

export type ChangeTicketLevelRequest = z.infer<
  typeof changeTicketLevelRequestSchema
>;

export const commentRequestSchema = z.object({
  text: z.string().min(1, 'Comment is required').max(2000),
});

export type CommentRequest = z.infer<typeof commentRequestSchema>;

export const ticketEventSchema = z.object({
  id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  event_type: z.string(),
  actor_user_id: z.string().uuid(),
  actor_name: z.string(),
  changes: z.record(z.any()),
  metadata: z.record(z.any()).optional(),
  created_at: z.string(),
});

export type TicketEvent = z.infer<typeof ticketEventSchema>;