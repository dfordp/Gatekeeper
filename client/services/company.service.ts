// client/services/company.service.ts
import { apiClient } from "@/lib/api-client"

export interface Company {
  id: string
  name: string
  created_at: string
  user_count?: number
  ticket_count?: number
}

export interface CompaniesResponse {
  companies: Company[]
  total: number
  limit: number
  offset: number
}

export const companyService = {
  async createCompany(name: string): Promise<Company> {
    const response = await apiClient.post<Company>("/api/companies/create", { name })
    return response.data
  },

  async getCompanies(limit: number = 100, offset: number = 0): Promise<CompaniesResponse> {
    const response = await apiClient.get<CompaniesResponse>(
      `/api/companies?limit=${limit}&offset=${offset}`
    )
    return response.data
  },

  async getCompanyById(companyId: string): Promise<Company> {
    const response = await apiClient.get<Company>(`/api/companies/${companyId}`)
    return response.data
  },
}