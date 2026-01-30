// client/app/dashboard/tickets/page.tsx

"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import TicketsTable from "@/components/dashboard/TicketsTable"
import CreateTicketDialog from "@/components/dashboard/tickets/CreateTicketDialog"
import { ticketService, Ticket } from "@/services/ticket.service"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, AlertCircle } from "lucide-react"

const STATUS_FILTERS = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
  { value: "reopened", label: "Reopened" },
]

export default function TicketsPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading, admin } = useAuth()
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [total, setTotal] = useState(0)
  const [ticketsLoading, setTicketsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchTickets()
    }
  }, [isAuthenticated, statusFilter, searchQuery, offset])

  const fetchTickets = async () => {
    try {
      setTicketsLoading(true)
      setError(null)

      const result = await ticketService.getTickets(
        limit,
        offset,
        statusFilter || undefined,
        searchQuery || undefined
      )

      setTickets(result.tickets)
      setTotal(result.total)
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(
        error.response?.data?.detail || "Failed to load tickets"
      )
      setTickets([])
    } finally {
      setTicketsLoading(false)
    }
  }

  const handleRefresh = () => {
    setOffset(0)
    fetchTickets()
  }

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    setOffset(0)
  }

  const handleStatusFilter = (status: string | null) => {
    setStatusFilter(status)
    setOffset(0)
  }

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  // Get company ID from admin user - needed for creating tickets
  const companyId = admin?.company_id || ""

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header with Create Button */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Tickets</h1>
            <p className="text-gray-600 mt-1">
              {total > 0
                ? `Showing ${offset + 1}-${Math.min(offset + limit, total)} of ${total} tickets`
                : "No tickets found"}
            </p>
          </div>
          {isAuthenticated && admin && (
            <CreateTicketDialog
              currentUserId={admin.id}
              onTicketCreated={handleRefresh}
            />
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-4">
          <Input
            placeholder="Search by ticket #, subject..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="flex-1"
          />
          <div className="flex gap-2 w-full md:w-auto">
            <Select
              value={statusFilter || "all"}
              onValueChange={(value) =>
                handleStatusFilter(value === "all" ? null : value)
              }
            >
              <SelectTrigger className="w-full md:w-48">
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                {STATUS_FILTERS.map((filter) => (
                  <SelectItem key={filter.value} value={filter.value}>
                    {filter.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {statusFilter && (
              <Button
                variant="outline"
                onClick={() => handleStatusFilter(null)}
                className="px-2"
                title="Clear filter"
              >
                ✕
              </Button>
            )}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Loading State */}
        {ticketsLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          </div>
        )}

        {/* Tickets Table */}
        {!ticketsLoading && (
          <TicketsTable
            tickets={tickets}
            onRefresh={handleRefresh}
          />
        )}

        {/* Pagination */}
        {!ticketsLoading && total > limit && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-600">
              Page {currentPage} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  setOffset(
                    Math.min(offset + limit, (totalPages - 1) * limit)
                  )
                }
                disabled={currentPage >= totalPages}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  )
}