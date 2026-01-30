// client/src/lib/api-client.ts
import axios, { AxiosInstance, AxiosError } from "axios"
import { API_BASE_URL } from "./constants"

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        "Content-Type": "application/json",
      },
    })

    // Add request interceptor to include auth token
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem("auth_token")
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Add response interceptor to handle errors
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Clear token and redirect to login
          localStorage.removeItem("auth_token")
          localStorage.removeItem("admin_user")
          window.location.href = "/login"
        }
        return Promise.reject(error)
      }
    )
  }

  get<T>(url: string, config = {}) {
    return this.client.get<T>(url, config)
  }

  post<T>(url: string, data = {}, config = {}) {
    return this.client.post<T>(url, data, config)
  }

  put<T>(url: string, data = {}, config = {}) {
    return this.client.put<T>(url, data, config)
  }

  patch<T>(url: string, data = {}, config = {}) {
    return this.client.patch<T>(url, data, config)
  }

  delete<T>(url: string, config = {}) {
    return this.client.delete<T>(url, config)
  }
}

export const apiClient = new ApiClient()