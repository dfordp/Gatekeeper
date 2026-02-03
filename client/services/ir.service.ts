// client/services/ir.service.ts
import { apiClient } from "@/lib/api-client"

export interface IncidentReport {
  id: string
  ir_number: string
  ticket_id: string
  vendor: string
  status: "open" | "in_progress" | "resolved" | "closed"
  expected_resolution_date?: string
  resolved_at?: string
  notes?: string
  vendor_status?: string
  vendor_notes?: string
  last_vendor_update?: string
  created_at: string
  updated_at: string
}

export interface OpenIR extends IncidentReport {
  days_open: number
}

export const irService = {
  // Open a new IR for a ticket
  async openIR(
    ticketId: string,
    data: {
      ir_number: string
      vendor?: string
      expected_resolution_date?: string
      notes?: string
      created_by_user_id?: string
    }
  ): Promise<IncidentReport> {
    const response = await apiClient.post(
      `/api/tickets/${ticketId}/ir/open`,
      data
    )
    return response.data
  },

  // Update IR status
  async updateIRStatus(
    irId: string,
    data: {
      status: string
      vendor_status?: string
      vendor_notes?: string
      notes?: string
      updated_by_user_id?: string
    }
  ): Promise<IncidentReport> {
    const response = await apiClient.put(
      `/api/ir/${irId}/status`,
      data
    )
    return response.data
  },

  // Close an IR
  async closeIR(
    irId: string,
    data: {
      resolution_notes?: string
      closed_by_user_id?: string
    }
  ): Promise<IncidentReport> {
    const response = await apiClient.post(
      `/api/ir/${irId}/close`,
      data
    )
    return response.data
  },

  // Get IR details
  async getIR(irId: string): Promise<IncidentReport> {
    const response = await apiClient.get(`/api/ir/${irId}`)
    return response.data
  },

  // Get all IRs for a ticket
  async getTicketIRs(ticketId: string): Promise<IncidentReport[]> {
    const response = await apiClient.get(
      `/api/tickets/${ticketId}/ir`
    )
    return response.data
  },

  // Get all open IRs
  async getOpenIRs(): Promise<OpenIR[]> {
    const response = await apiClient.get(`/api/ir/open`)
    return response.data
  },
}