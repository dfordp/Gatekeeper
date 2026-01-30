// client/src/hooks/useAuth.ts
"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { authService } from "@/services/auth.service"
import { Admin } from "@/types"

export function useAuth() {
  const router = useRouter()
  const [admin, setAdmin] = useState<Admin | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = authService.getToken()
        if (!token) {
          setIsAuthenticated(false)
          setIsLoading(false)
          return
        }

        const currentAdmin = await authService.getCurrentAdmin()
        setAdmin(currentAdmin)
        authService.setAdmin(currentAdmin)
        setIsAuthenticated(true)
      } catch (error) {
        authService.logout()
        setIsAuthenticated(false)
      } finally {
        setIsLoading(false)
      }
    }

    checkAuth()
  }, [])

  const login = async (email: string, password: string) => {
    const response = await authService.login({ email, password })
    authService.setToken(response.token)
    authService.setAdmin(response.admin as Admin)
    setAdmin(response.admin as Admin)
    setIsAuthenticated(true)
    router.push("/dashboard")
  }

  const register = async (email: string, password: string, full_name: string, secret_key: string, company_id?: string) => {
    const response = await authService.register({
      email,
      password,
      full_name,
      secret_key,
      company_id,
    })
    authService.setToken(response.token)
    authService.setAdmin(response.admin as Admin)
    setAdmin(response.admin as Admin)
    setIsAuthenticated(true)
    router.push("/dashboard")
  }

  const logout = () => {
    authService.logout()
    setAdmin(null)
    setIsAuthenticated(false)
    router.push("/login")
  }

  return {
    admin,
    isLoading,
    isAuthenticated,
    login,
    register,
    logout,
  }
}