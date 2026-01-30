// client/src/services/auth.service.ts
import { apiClient } from "@/lib/api-client"
import { AuthResponse, LoginCredentials, RegisterCredentials, Admin, ChangePasswordRequest } from "@/types"

export const authService = {
  register: async (credentials: RegisterCredentials): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>("/api/admin/register", credentials)
    return response.data
  },

  login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>("/api/admin/login", credentials)
    return response.data
  },

  getCurrentAdmin: async (): Promise<Admin> => {
    const response = await apiClient.get<Admin>("/api/admin/me")
    return response.data
  },

  changePassword: async (data: ChangePasswordRequest): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>("/api/admin/change-password", data)
    return response.data
  },

  logout: () => {
    localStorage.removeItem("auth_token")
    localStorage.removeItem("admin_user")
  },

  setToken: (token: string) => {
    localStorage.setItem("auth_token", token)
  },

  getToken: () => {
    return localStorage.getItem("auth_token")
  },

  setAdmin: (admin: Admin) => {
    localStorage.setItem("admin_user", JSON.stringify(admin))
  },

  getAdmin: () => {
    const admin = localStorage.getItem("admin_user")
    return admin ? JSON.parse(admin) : null
  },

  isAuthenticated: () => {
    return !!localStorage.getItem("auth_token")
  },
}