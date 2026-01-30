// client/services/user.service.ts
import { apiClient } from "@/lib/api-client"

export interface User {
  id: string
  name: string
  email: string
  phone_number?: string
  role: string
  company_id: string
  company_name?: string
  created_at: string
}

export interface CreateUserRequest {
  name: string
  email: string
  company_id: string
  role: string
  phone_number?: string
}

export interface UsersResponse {
  users: User[]
  total: number
  limit: number
  offset: number
}

export const userService = {
  async getUsers(
    companyId?: string,
    role?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<UsersResponse> {
    const params = new URLSearchParams()
    if (companyId) params.append('company_id', companyId)
    if (role) params.append('role', role)
    params.append('limit', limit.toString())
    params.append('offset', offset.toString())

    const response = await apiClient.get<UsersResponse>(`/api/users?${params.toString()}`)
    return response.data
  },

  async getUser(userId: string): Promise<User> {
    const response = await apiClient.get<User>(`/api/users/${userId}`)
    return response.data
  },

  async createUser(data: CreateUserRequest): Promise<User> {
    const response = await apiClient.post<User>('/api/users', data)
    return response.data
  },

  async updateUser(userId: string, data: Partial<CreateUserRequest>): Promise<User> {
    const response = await apiClient.put<User>(`/api/users/${userId}`, data)
    return response.data
  },

  async deleteUser(userId: string): Promise<{ message: string }> {
    const response = await apiClient.delete<{ message: string }>(`/api/users/${userId}`)
    return response.data
  },
}