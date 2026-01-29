import { z } from 'zod';

export const rcaStatusSchema = z.enum([
  'draft',
  'pending_approval',
  'approved',
  'deprecated',
]);
export type RCAStatus = z.infer<typeof rcaStatusSchema>;

export const rcaSchema = z.object({
  id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  company_id: z.string().uuid(),
  status: rcaStatusSchema,
  root_cause: z.string(),
  corrective_actions: z.string(),
  prevention_measures: z.string(),
  submitted_by: z.string().uuid().nullable(),
  submitted_at: z.string().nullable(),
  approved_by: z.string().uuid().nullable(),
  approved_at: z.string().nullable(),
  rejection_reason: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type RCA = z.infer<typeof rcaSchema>;

export const createRCARequestSchema = z.object({
  root_cause: z
    .string()
    .min(1, 'Root cause is required')
    .max(5000),
  corrective_actions: z
    .string()
    .min(1, 'Corrective actions are required')
    .max(5000),
  prevention_measures: z
    .string()
    .min(1, 'Prevention measures are required')
    .max(5000),
});

export type CreateRCARequest = z.infer<typeof createRCARequestSchema>;

export const updateRCARequestSchema = createRCARequestSchema;
export type UpdateRCARequest = z.infer<typeof updateRCARequestSchema>;

export const submitRCARequestSchema = z.object({
  comment: z.string().optional(),
});

export type SubmitRCARequest = z.infer<typeof submitRCARequestSchema>;

export const approveRCARequestSchema = z.object({
  feedback: z.string().optional(),
});

export type ApproveRCARequest = z.infer<typeof approveRCARequestSchema>;

export const rejectRCARequestSchema = z.object({
  reason: z
    .string()
    .min(1, 'Rejection reason is required')
    .max(1000),
});

export type RejectRCARequest = z.infer<typeof rejectRCARequestSchema>;

export const rcaEventSchema = z.object({
  id: z.string().uuid(),
  rca_id: z.string().uuid(),
  event_type: z.string(),
  actor_user_id: z.string().uuid(),
  actor_name: z.string(),
  changes: z.record(z.any()),
  metadata: z.record(z.any()).optional(),
  created_at: z.string(),
});

export type RCAEvent = z.infer<typeof rcaEventSchema>;