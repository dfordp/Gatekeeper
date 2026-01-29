import { z } from 'zod';

export const loginRequestSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

export type LoginRequest = z.infer<typeof loginRequestSchema>;

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  name: z.string(),
  company_id: z.string().uuid(),
  role: z.enum(['platform_admin', 'company_admin', 'engineer', 'requester']),
  created_at: z.string(),
  updated_at: z.string(),
});

export type User = z.infer<typeof userSchema>;

export const loginResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    access_token: z.string(),
    refresh_token: z.string(),
    user: userSchema,
  }),
});

export type LoginResponse = z.infer<typeof loginResponseSchema>;