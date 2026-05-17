// client/types/index.ts

export interface Admin {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
  last_login?: string
  temporary_password?: string
  company_id?: string
}

export interface AuthResponse {
  token: string
  admin: Admin
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterCredentials {
  email: string
  password: string
  full_name: string
  secret_key: string
  company_id?: string
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export interface TicketEvent {
  id: string
  event_type: string
  actor_user_id: string
  actor: string | null
  payload: Record<string, unknown>
  created_at: string
}
export interface TicketDetail {
  id: string
  ticket_no: string
  subject: string
  summary: string | null
  detailed_description: string
  status: "open" | "in_progress" | "resolved" | "closed" | "reopened"
  category: string | null
  level: string | null
  company_id: string
  company_name: string | null
  created_by: string | null
  created_by_id: string | null
  assigned_to: string | null
  assigned_to_id: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
  reopened_at: string | null
  attachment_ids: string[]
  events: TicketEvent[]
}

export interface User {
  id: string
  email: string
  name: string
  role: string
  company_id?: string
}