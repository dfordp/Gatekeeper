// client/components/dashboard/users/UsersTable.tsx
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { RefreshCw, Trash2, Users } from "lucide-react"

interface User {
  id: string
  name: string
  email: string
  phone_number?: string
  role: string
  company_name?: string
  created_at: string
}

interface UsersTableProps {
  users: User[] | null | undefined
  onDelete: (userId: string) => void
  onRefresh: () => void
}

const roleColors: Record<string, string> = {
  support_engineer: "bg-blue-100 text-blue-800",
  supervisor: "bg-purple-100 text-purple-800",
}

const EmptyState = () => (
  <div className="flex flex-col items-center justify-center py-12">
    <Users className="h-12 w-12 text-gray-400 mb-4" />
    <h3 className="text-lg font-medium text-gray-900 mb-1">No users found</h3>
    <p className="text-gray-500">Add a new team member to get started.</p>
  </div>
)

export default function UsersTable({ users, onDelete, onRefresh }: UsersTableProps) {
  const [refreshing, setRefreshing] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleRefresh = async () => {
    setRefreshing(true)
    await onRefresh()
    setRefreshing(false)
  }

  const handleDelete = async (userId: string) => {
    if (!confirm("Are you sure you want to delete this user?")) return

    setDeletingId(userId)
    setDeleteError(null)
    try {
      await onDelete(userId)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete user"
      setDeleteError(message)
    } finally {
      setDeletingId(null)
    }
  }

  const userList = users && Array.isArray(users) ? users : []
  const hasUsers = userList.length > 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Team Members ({userList.length})</CardTitle>
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
        {deleteError && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{deleteError}</AlertDescription>
          </Alert>
        )}
        
        {!hasUsers ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4">Name</th>
                  <th className="text-left py-3 px-4">Email</th>
                  <th className="text-left py-3 px-4">Role</th>
                  <th className="text-left py-3 px-4">Company</th>
                  <th className="text-left py-3 px-4">Phone</th>
                  <th className="text-left py-3 px-4">Joined</th>
                  <th className="text-right py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {userList.map((user) => (
                  <tr key={user.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium">{user.name || <span className="text-gray-400">—</span>}</td>
                    <td className="py-3 px-4">{user.email || <span className="text-gray-400">—</span>}</td>
                    <td className="py-3 px-4">
                      <Badge className={roleColors[user.role] || "bg-gray-100"}>
                        {user.role.replace('_', ' ')}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      {user.company_name || <span className="text-gray-400 italic">Unknown</span>}
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {user.phone_number || <span className="text-gray-400">—</span>}
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {user.created_at
                        ? new Date(user.created_at).toLocaleDateString()
                        : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(user.id)}
                        disabled={deletingId === user.id}
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