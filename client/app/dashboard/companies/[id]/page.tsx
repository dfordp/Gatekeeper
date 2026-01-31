// client/app/dashboard/companies/[id]/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import { companyService, Company } from "@/services/company.service"
import { userService, User } from "@/services/user.service"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2, AlertCircle, Plus, ArrowLeft, Trash2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export default function CompanyDetailPage() {
  const router = useRouter()
  const params = useParams()
  const { isAuthenticated, isLoading } = useAuth()
  const [company, setCompany] = useState<Company | null>(null)
  const [externalUsers, setExternalUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Add user dialog state
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUserName, setNewUserName] = useState("")
  const [newUserEmail, setNewUserEmail] = useState("")
  const [creatingUser, setCreatingUser] = useState(false)
  const [addUserError, setAddUserError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated && params.id) {
      fetchCompanyDetails()
    }
  }, [isAuthenticated, params.id])

  const fetchCompanyDetails = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const companyId = params.id as string
      const result = await companyService.getCompanies(500)
      const selectedCompany = result.companies.find(c => c.id === companyId)
      
      if (!selectedCompany) {
        setError("Company not found")
        return
      }
      
      setCompany(selectedCompany)
      
      // Fetch external users for this company
      const usersResult = await userService.getUsers(companyId, undefined, 500)
      const externalUsersFiltered = usersResult.users?.filter(u => u.role === "external") || []
      setExternalUsers(externalUsersFiltered)
    } catch (err) {
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || "Failed to load company")
    } finally {
      setLoading(false)
    }
  }

  const handleAddUser = async () => {
    setAddUserError(null)

    if (!newUserName.trim()) {
      setAddUserError("Name is required")
      return
    }

    if (!newUserEmail.trim()) {
      setAddUserError("Email is required")
      return
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(newUserEmail)) {
      setAddUserError("Invalid email format")
      return
    }

    try {
      setCreatingUser(true)
      const newUser = await userService.createUser({
        name: newUserName.trim(),
        email: newUserEmail.trim(),
        company_id: company!.id,
        role: "external",
      })
      
      setExternalUsers([...externalUsers, newUser])
      setNewUserName("")
      setNewUserEmail("")
      setShowAddUser(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create user"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setAddUserError(apiError?.response?.data?.detail || errorMessage)
    } finally {
      setCreatingUser(false)
    }
  }

  const handleDeleteUser = async (userId: string) => {
    if (!window.confirm("Are you sure you want to delete this user?")) return

    try {
      await userService.deleteUser(userId)
      setExternalUsers(externalUsers.filter(u => u.id !== userId))
    } catch (err) {
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || "Failed to delete user")
    }
  }

  if (isLoading || loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
        </div>
      </DashboardLayout>
    )
  }

  if (error || !company) {
    return (
      <DashboardLayout>
        <div className="space-y-4">
          <Button variant="outline" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error || "Company not found"}</AlertDescription>
          </Alert>
        </div>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="outline" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{company.name}</h1>
            <p className="text-sm text-gray-500">External Users Management</p>
          </div>
        </div>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>External Users</CardTitle>
            <Dialog open={showAddUser} onOpenChange={setShowAddUser}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4 mr-2" />
                  Add User
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Add External User</DialogTitle>
                  <DialogDescription>
                    Add a new external user to {company.name}
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                  {addUserError && (
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{addUserError}</AlertDescription>
                    </Alert>
                  )}

                  <div className="space-y-2">
                    <Label htmlFor="name">Full Name *</Label>
                    <Input
                      id="name"
                      placeholder="e.g., John Doe"
                      value={newUserName}
                      onChange={(e) => setNewUserName(e.target.value)}
                      disabled={creatingUser}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">Email *</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="e.g., john@example.com"
                      value={newUserEmail}
                      onChange={(e) => setNewUserEmail(e.target.value)}
                      disabled={creatingUser}
                    />
                  </div>

                  <div className="flex gap-2 justify-end">
                    <Button
                      variant="outline"
                      onClick={() => setShowAddUser(false)}
                      disabled={creatingUser}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleAddUser}
                      disabled={creatingUser || !newUserName.trim() || !newUserEmail.trim()}
                    >
                      {creatingUser && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                      {creatingUser ? "Creating..." : "Add User"}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent>
            {externalUsers.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No external users yet</p>
            ) : (
              <div className="space-y-2">
                {externalUsers.map((user) => (
                  <div
                    key={user.id}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div>
                      <p className="font-medium text-gray-900">{user.name}</p>
                      <p className="text-sm text-gray-500">{user.email}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteUser(user.id)}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  )
}