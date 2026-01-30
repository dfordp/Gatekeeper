// client/app/dashboard/companies/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import { companyService, Company } from "@/services/company.service"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2, AlertCircle, Plus, Building2 } from "lucide-react"

export default function CompaniesPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading, admin } = useAuth()
  const [companies, setCompanies] = useState<Company[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [newCompanyName, setNewCompanyName] = useState("")
  const [creatingCompany, setCreatingCompany] = useState(false)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchCompanies()
    }
  }, [isAuthenticated])

  // Check if user is admin or manager
  const canManageCompanies = admin?.role === "admin" || admin?.role === "manager"

  const fetchCompanies = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await companyService.getCompanies(500)
      setCompanies(result.companies)
    } catch (err) {
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || "Failed to load companies")
    } finally {
      setLoading(false)
    }
  }

  const handleCreateCompany = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!newCompanyName.trim()) {
      setError("Company name is required")
      return
    }

    try {
      setCreatingCompany(true)
      const newCompany = await companyService.createCompany(newCompanyName)
      setCompanies([newCompany, ...companies])
      setNewCompanyName("")
      setShowForm(false)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create company"
      const apiError = err as { response?: { data?: { detail?: string } } }
      setError(apiError?.response?.data?.detail || errorMessage)
    } finally {
      setCreatingCompany(false)
    }
  }

  if (!isAuthenticated || !canManageCompanies) {
    return (
      <DashboardLayout>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            You don&apos;t have permission to access this page. Only admins and managers can manage companies.
          </AlertDescription>
        </Alert>
      </DashboardLayout>
    )
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Companies</h1>
            <p className="text-gray-600 mt-1">
              Manage support ticket dashboard companies
            </p>
          </div>
          <Button onClick={() => setShowForm(!showForm)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Company
          </Button>
        </div>

        {/* Create Company Form */}
        {showForm && (
          <Card className="border-blue-200 bg-blue-50">
            <CardHeader>
              <CardTitle className="text-lg">Add New Company</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateCompany} className="space-y-4">
                {error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <div className="space-y-2">
                  <Label htmlFor="companyName" className="font-semibold">
                    Company Name
                  </Label>
                  <Input
                    id="companyName"
                    placeholder="Enter company name"
                    value={newCompanyName}
                    onChange={(e) => setNewCompanyName(e.target.value)}
                    disabled={creatingCompany}
                    className="min-h-10"
                  />
                </div>

                <div className="flex gap-2 justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowForm(false)
                      setNewCompanyName("")
                      setError(null)
                    }}
                    disabled={creatingCompany}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={creatingCompany || !newCompanyName.trim()}>
                    {creatingCompany && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    Create Company
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Error Alert */}
        {error && !showForm && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          </div>
        )}

        {/* Companies Grid */}
        {!loading && companies.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((company) => (
              <Card key={company.id} className="hover:shadow-lg transition-shadow">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Building2 className="h-5 w-5 text-blue-600" />
                    {company.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase">Users</p>
                      <p className="text-2xl font-bold text-gray-900">{company.user_count || 0}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase">Tickets</p>
                      <p className="text-2xl font-bold text-gray-900">{company.ticket_count || 0}</p>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">
                    Created {new Date(company.created_at).toLocaleDateString()}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          !loading && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Building2 className="h-12 w-12 text-gray-400 mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-1">No companies yet</h3>
                <p className="text-gray-500 text-center">
                  Click &quot;Add Company&quot; to create your first support ticket dashboard company
                </p>
              </CardContent>
            </Card>
          )
        )}
      </div>
    </DashboardLayout>
  )
}