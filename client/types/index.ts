// client/src/types/index.ts
export interface Admin {
  id: string
  email: string
  full_name: string
  role: "admin" | "manager" | "analyst"
  is_active: boolean
  company_id?: string
  last_login?: string
  created_at: string
}

export interface AuthResponse {
  token: string
  admin: Omit<Admin, "is_active" | "created_at" | "last_login">
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterCredentials {
  email: string
  password: string
  full_name: string
  company_id?: string
  secret_key: string
}

export interface ChangePasswordRequest {
  old_password: string
  new_password: string
}

export interface ApiResponse<T> {
  data?: T
  error?: string
  message?: string
}

export interface PaginationMeta {
  page: number
  per_page: number
  total: number
  total_pages: number
}