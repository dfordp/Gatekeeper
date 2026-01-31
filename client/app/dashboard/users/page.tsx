// client/app/dashboard/users/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import UsersTable from "@/components/dashboard/users/UsersTable"
import AddUserDialog from "@/components/dashboard/users/AddUserDialog"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2, Plus } from "lucide-react"
import { userService } from "@/services/user.service"

interface User {
  id: string
  name: string
  email: string
  phone_number?: string
  role: string
  company_id: string
  company_name?: string
  created_at: string
}

export default function UsersPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openDialog, setOpenDialog] = useState(false)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchUsers()
    }
  }, [isAuthenticated, refreshTrigger])

  const fetchUsers = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await userService.getUsers(undefined, undefined, 500)
      // Filter out external users - only show internal support team
      const internalUsers = result.users?.filter(u => u.role !== "external") || []
      setUsers(internalUsers)
    } catch (err) {
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || "Failed to load users")
    } finally {
      setLoading(false)
    }
  }

  const handleUserCreated = () => {
    setOpenDialog(false)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleUserDeleted = async (userId: string) => {
    if (!confirm("Are you sure you want to delete this user?")) return

    try {
      await userService.deleteUser(userId)
      setUsers(users.filter(u => u.id !== userId))
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete user"
      setError(message)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Users</h1>
            <p className="text-gray-600">Manage support team members</p>
          </div>
          <Button onClick={() => setOpenDialog(true)} className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add User
          </Button>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <UsersTable users={users} onDelete={handleUserDeleted} onRefresh={fetchUsers} />
        )}

        <AddUserDialog open={openDialog} onOpenChange={setOpenDialog} onUserCreated={handleUserCreated} />
      </div>
    </DashboardLayout>
  )
}