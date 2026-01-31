// client/types/index.ts

export interface TicketEvent {
  actor_name: string
  id: string
  type: string
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