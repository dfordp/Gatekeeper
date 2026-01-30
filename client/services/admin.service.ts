// client/services/admin.service.ts
import { apiClient } from "@/lib/api-client"

export interface Admin {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
  last_login?: string
  temporary_password?: string
}

export interface CreateAdminRequest {
  email: string
  full_name: string
  role: string
}

export interface AdminsResponse {
  admins: Admin[]
  total: number
  limit: number
  offset: number
}

export const adminService = {
  async getAdmins(limit: number = 100, offset: number = 0): Promise<AdminsResponse> {
    const response = await apiClient.get<AdminsResponse>(
      `/api/admin-management/admins?limit=${limit}&offset=${offset}`
    )
    return response.data
  },

  async createAdmin(data: CreateAdminRequest): Promise<Admin> {
    const response = await apiClient.post<Admin>('/api/admin-management/admins', data)
    return response.data
  },

  async updateAdmin(adminId: string, data: Partial<CreateAdminRequest>): Promise<Admin> {
    const response = await apiClient.put<Admin>(`/api/admin-management/admins/${adminId}`, data)
    return response.data
  },

  async deleteAdmin(adminId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/admin-management/admins/${adminId}`)
    return response.data
  },
}