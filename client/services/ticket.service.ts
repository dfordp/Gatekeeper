// client/services/ticket.service.ts
import { apiClient } from "@/lib/api-client"

// ==================== TYPES ====================

export interface TicketEvent {
  id: string
  type: string
  actor: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface Attachment {
  id: string
  ticket_id: string
  file_name: string
  type: string
  file_path: string
  file_size?: number
  mime_type?: string
  cloudinary_url?: string
  created_at: string
}

export interface RootCauseAnalysis {
  id: string
  ticket_id: string
  root_cause_description: string
  contributing_factors: string[]
  prevention_measures?: string
  resolution_steps: string[]
  related_ticket_ids: string[]
  created_at: string
}

export interface ResolutionNote {
  id: string
  ticket_id: string
  solution_description: string
  steps_taken: string[]
  resources_used: string[]
  follow_up_notes?: string
  created_at: string
}

export interface Analytics {
  [key: string]: string | number | boolean | Analytics | (string | number | boolean | Analytics)[]
}

export interface Ticket {
  id: string
  ticket_no: string
  subject: string
  status: string
  category?: string | null
  level?: string | null
  company_id?: string
  company_name?: string | null
  created_by?: string | null
  assigned_to?: string | null
  created_at: string
  updated_at: string
  closed_at?: string | null
}

export interface TicketDetail extends Ticket {
  rca: any
  summary?: string | null
  detailed_description: string
  created_by_id?: string | null
  assigned_to_id?: string | null
  reopened_at?: string | null
  attachment_ids: string[]
  events: TicketEvent[]
  attachments?: Attachment[]
  root_cause_analysis?: RootCauseAnalysis
  resolution_note?: ResolutionNote
}

export interface TicketsListResponse {
  tickets: Ticket[]
  total: number
  limit: number
  offset: number
}

// ==================== REQUEST TYPES ====================

export interface CreateTicketRequest {
  subject: string
  detailed_description: string
  company_id: string
  raised_by_user_id: string
  summary?: string
  category?: string
  level?: string
  assigned_engineer_id?: string
  created_at?: string
  ticket_no?: string
  status?: string
  closed_at?: string | null
}

export interface AddAttachmentRequest {
  file_path: string
  file_name: string
  attachment_type: string
  mime_type?: string
  file_size?: number
  cloudinary_url?: string
  created_by_user_id?: string
}

export interface AddRCARequest {
  root_cause_description: string
  created_by_user_id: string
  contributing_factors?: string[]
  prevention_measures?: string
  resolution_steps?: string[]
  related_ticket_ids?: string[]
  ticket_closed_at?: string | null
}

export interface AddResolutionNoteRequest {
  solution_description: string
  created_by_user_id: string
  steps_taken?: string[]
  resources_used?: string[]
  follow_up_notes?: string
}

// ==================== SERVICE ====================

export const ticketService = {
  // Get list of tickets with filters
  async getTickets(
    limit: number = 50,
    offset: number = 0,
    status?: string,
    search?: string
  ): Promise<TicketsListResponse> {
    const params = new URLSearchParams()
    params.append("limit", limit.toString())
    params.append("offset", offset.toString())
    if (status) params.append("status", status)
    if (search) params.append("search", search)

    const response = await apiClient.get<TicketsListResponse>(
      `/api/dashboard/tickets?${params.toString()}`
    )
    return response.data
  },

  // Get single ticket details
  async getTicketById(ticketId: string): Promise<TicketDetail> {
    const response = await apiClient.get<TicketDetail>(
      `/api/dashboard/tickets/${ticketId}`
    )
    return response.data
  },

  // Update ticket status
  async updateStatus(
    ticketId: string,
    status: string
  ): Promise<{ id: string; ticket_no: string; status: string; updated_at: string }> {
    const response = await apiClient.put<{ id: string; ticket_no: string; status: string; updated_at: string }>(
      `/api/dashboard/tickets/${ticketId}/status`,
      { status }
    )
    return response.data
  },

  // Assign ticket to engineer
  async assignTicket(
    ticketId: string,
    engineerId: string
  ): Promise<{ id: string; ticket_no: string; assigned_to: string; assigned_to_id: string }> {
    const response = await apiClient.put<{ id: string; ticket_no: string; assigned_to: string; assigned_to_id: string }>(
      `/api/dashboard/tickets/${ticketId}/assign`,
      { engineer_id: engineerId }
    )
    return response.data
  },

  // Get analytics
  async getAnalytics(days: number = 30): Promise<Analytics> {
    const response = await apiClient.get<Analytics>(
      `/api/dashboard/analytics?days=${days}`
    )
    return response.data
  },

  // Create a new ticket
  async createTicket(data: CreateTicketRequest): Promise<Ticket> {
    const response = await apiClient.post<Ticket>("/api/tickets/create", data)
    return response.data
  },

  // Add attachment to ticket
  async addAttachment(
    ticketId: string,
    data: AddAttachmentRequest
  ): Promise<Attachment> {
    const response = await apiClient.post<Attachment>(
      `/api/tickets/${ticketId}/attachments`,
      data
    )
    return response.data
  },

  // Add Root Cause Analysis
  async addRCA(ticketId: string, data: AddRCARequest): Promise<RootCauseAnalysis> {
    const response = await apiClient.post<RootCauseAnalysis>(
      `/api/tickets/${ticketId}/rca`,
      data
    )
    return response.data
  },

  // Add Resolution Note
  async addResolutionNote(
    ticketId: string,
    data: AddResolutionNoteRequest
  ): Promise<ResolutionNote> {
    const response = await apiClient.post<ResolutionNote>(
      `/api/tickets/${ticketId}/resolution`,
      data
    )
    return response.data
  },

  async deleteTicket(ticketId: string): Promise<{ message: string }> {
  const response = await apiClient.delete<{ message: string }>(
    `/api/tickets/${ticketId}`
  )
  return response.data
},

  async updateTicket(ticketId: string, data: {
    subject?: string
    summary?: string
    detailed_description?: string
    category?: string
    level?: string
  }): Promise<any> {
    const response = await apiClient.put(
      `/api/tickets/${ticketId}`,
      data
    )
    return response.data
  },
}

