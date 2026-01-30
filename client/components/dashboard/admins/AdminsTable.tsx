// client/components/dashboard/admins/AdminsTable.tsx
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { RefreshCw, Trash2, Shield } from "lucide-react"

interface Admin {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
  last_login?: string
}

interface AdminsTableProps {
  admins: Admin[] | null | undefined
  onDelete: (adminId: string) => void
  onRefresh: () => void
}

const roleColors: Record<string, string> = {
  admin: "bg-red-100 text-red-800",
  manager: "bg-blue-100 text-blue-800",
  analyst: "bg-green-100 text-green-800",
}

const EmptyState = () => (
  <div className="flex flex-col items-center justify-center py-12">
    <Shield className="h-12 w-12 text-gray-400 mb-4" />
    <h3 className="text-lg font-medium text-gray-900 mb-1">No admins found</h3>
    <p className="text-gray-500">Create a new administrator to get started.</p>
  </div>
)

export default function AdminsTable({ admins, onDelete, onRefresh }: AdminsTableProps) {
  const [refreshing, setRefreshing] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleRefresh = async () => {
    setRefreshing(true)
    await onRefresh()
    setRefreshing(false)
  }

  const handleDelete = async (adminId: string) => {
    setDeletingId(adminId)
    await onDelete(adminId)
    setDeletingId(null)
  }

  const adminList = admins && Array.isArray(admins) ? admins : []
  const hasAdmins = adminList.length > 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Administrators ({adminList.length})</CardTitle>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
        </Button>
      </CardHeader>
      <CardContent>
        {!hasAdmins ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4">Name</th>
                  <th className="text-left py-3 px-4">Email</th>
                  <th className="text-left py-3 px-4">Role</th>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-left py-3 px-4">Created</th>
                  <th className="text-left py-3 px-4">Last Login</th>
                  <th className="text-right py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {adminList.map((admin) => (
                  <tr key={admin.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium">{admin.full_name || <span className="text-gray-400">—</span>}</td>
                    <td className="py-3 px-4">{admin.email}</td>
                    <td className="py-3 px-4">
                      <Badge className={roleColors[admin.role] || "bg-gray-100"}>
                        {admin.role}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      {admin.is_active ? (
                        <Badge className="bg-green-100 text-green-800">Active</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-800">Inactive</Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {admin.created_at
                        ? new Date(admin.created_at).toLocaleDateString()
                        : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {admin.last_login
                        ? new Date(admin.last_login).toLocaleDateString()
                        : <span className="text-gray-400">Never</span>}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(admin.id)}
                        disabled={deletingId === admin.id}
                        className="text-red-600 hover:text-red-800"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}