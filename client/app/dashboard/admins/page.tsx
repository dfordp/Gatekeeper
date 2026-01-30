// client/app/dashboard/admins/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import AdminsTable from "@/components/dashboard/admins/AdminsTable"
import AddAdminDialog from "@/components/dashboard/admins/AddAdminDialog"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2, Plus, Lock } from "lucide-react"
import { adminService } from "@/services/admin.service"

interface Admin {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
  last_login?: string
}

export default function AdminsPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading, admin } = useAuth()
  const [admins, setAdmins] = useState<Admin[]>([])
  const [loading, setLoading] = useState(true)
  const [, setError] = useState<string | null>(null)
  const [openDialog, setOpenDialog] = useState(false)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // Check if user has admin role
  const isAdmin = admin?.role === "admin"

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated && isAdmin) {
      fetchAdmins()
    }
  }, [isAuthenticated, isAdmin, refreshTrigger])

  const fetchAdmins = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await adminService.getAdmins()
      setAdmins(data.admins || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load admins"
      setError(message)
      setAdmins([])
    } finally {
      setLoading(false)
    }
  }

  const handleAdminCreated = () => {
    setOpenDialog(false)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleAdminDeleted = async (adminId: string) => {
    if (!confirm("Are you sure you want to delete this admin?")) return

    try {
      await adminService.deleteAdmin(adminId)
      setAdmins(admins.filter(a => a.id !== adminId))
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete admin"
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

  if (!isAdmin) {
    return (
      <DashboardLayout>
        <div className="flex flex-col items-center justify-center min-h-screen">
          <Lock className="h-16 w-16 text-gray-400 mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
          <p className="text-gray-600 mb-4">Only administrators can access this page</p>
          <Button onClick={() => router.push("/dashboard")}>Back to Dashboard</Button>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Admin Management</h1>
            <p className="text-gray-600">Manage system administrators</p>
          </div>
          <Button onClick={() => setOpenDialog(true)} className="flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Create Admin
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <AdminsTable admins={admins} onDelete={handleAdminDeleted} onRefresh={fetchAdmins} />
        )}

        <AddAdminDialog open={openDialog} onOpenChange={setOpenDialog} onAdminCreated={handleAdminCreated} />
      </div>
    </DashboardLayout>
  )
}