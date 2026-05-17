// client/app/dashboard/tickets/page.tsx

"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import TicketsTable from "@/components/dashboard/TicketsTable"
import CreateTicketDialog from "@/components/dashboard/tickets/CreateTicketDialog"
import { ticketService, Ticket } from "@/services/ticket.service"
import { companyService, Company } from "@/services/company.service"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, AlertCircle, Download } from "lucide-react"

const STATUS_FILTERS = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "user_input_required", label: "User Input Required" },
  { value: "on_hold", label: "On Hold" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
  { value: "reopened", label: "Reopened" },
]

const LEVEL_FILTERS = [
  { value: "level-1", label: "Level 1 (Medium)" },
  { value: "level-2", label: "Level 2 (High)" },
  { value: "level-3", label: "Level 3 (Critical)" },
]

type SortColumn = "ticket_no" | "created_at" | "open_duration" | null
type SortOrder = "asc" | "desc"
type CsvRow = Record<string, string | number | boolean | null | undefined>

const EXPORT_PAGE_SIZE = 100

const emptyCell = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}

const formatDate = (value?: string | null) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString()
}

const fileNameFromPath = (path?: string | null) => {
  if (!path) return "-"
  const cleanPath = path.split("?")[0]
  return cleanPath.split("/").pop() || path
}

const joinList = (items?: unknown[]) => {
  if (!items || items.length === 0) return "-"
  return items.map(emptyCell).join("; ")
}

const escapeCsvCell = (value: unknown) => {
  const normalized = emptyCell(value).replace(/\r?\n|\r/g, " ")
  return `"${normalized.replace(/"/g, '""')}"`
}

const buildCsv = (rows: CsvRow[]) => {
  if (rows.length === 0) return ""
  const headers = Object.keys(rows[0])
  return [
    headers.map(escapeCsvCell).join(","),
    ...rows.map((row) => headers.map((header) => escapeCsvCell(row[header])).join(",")),
  ].join("\r\n")
}

export default function TicketsPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading, admin } = useAuth()
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [total, setTotal] = useState(0)
  const [ticketsLoading, setTicketsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [companies, setCompanies] = useState<Company[]>([])

  // Filters
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<string | null>(null)
  const [companyFilter, setCompanyFilter] = useState<string | null>(null)
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)
  
  // Sorting
  const [sortColumn, setSortColumn] = useState<SortColumn>(null)
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc")

  // Fetch companies after auth so the request has the JWT attached.
  useEffect(() => {
    const fetchCompanies = async () => {
      try {
        const pageSize = 500
        const allCompanies: Company[] = []
        let nextOffset = 0
        let expectedTotal = 0

        do {
          const response = await companyService.getCompanies(pageSize, nextOffset)
          allCompanies.push(...response.companies)
          expectedTotal = response.total
          nextOffset += pageSize
        } while (allCompanies.length < expectedTotal)

        setCompanies(allCompanies)
      } catch (err) {
        console.error("Failed to fetch companies:", err)
      }
    }

    if (!isAuthenticated) return
    fetchCompanies()
  }, [isAuthenticated])

  const fetchTickets = useCallback(async () => {
    try {
      setTicketsLoading(true)
      setError(null)

      const result = await ticketService.getTickets(
        limit,
        offset,
        statusFilter || undefined,
        undefined,
        companyFilter || undefined,
        levelFilter || undefined
      )

      let filteredTickets = result.tickets

      // Apply client-side sorting
      if (sortColumn) {
        filteredTickets = [...filteredTickets].sort((a, b) => {
          let aVal: string | number | Date = a[sortColumn as keyof Ticket] as string | number | Date
          let bVal: string | number | Date = b[sortColumn as keyof Ticket] as string | number | Date

          if (sortColumn === "open_duration") {
            // Calculate open duration for sorting
            const getOpenDays = (ticket: Ticket) => {
              const created = new Date(ticket.created_at)
              const closed = ticket.closed_at ? new Date(ticket.closed_at) : new Date()
              return (closed.getTime() - created.getTime()) / (1000 * 60 * 60 * 24)
            }
            aVal = getOpenDays(a)
            bVal = getOpenDays(b)
          }

          if (aVal < bVal) return sortOrder === "asc" ? -1 : 1
          if (aVal > bVal) return sortOrder === "asc" ? 1 : -1
          return 0
        })
      }

      setTickets(filteredTickets)
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
  }, [limit, offset, statusFilter, levelFilter, companyFilter, sortColumn, sortOrder])

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchTickets()
    }
  }, [isAuthenticated, fetchTickets])

  const handleStatusFilter = (status: string | null) => {
    setStatusFilter(status)
    setOffset(0)
  }

  const handleLevelFilter = (level: string | null) => {
    setLevelFilter(level)
    setOffset(0)
  }

  const handleCompanyFilter = (company: string | null) => {
    setCompanyFilter(company)
    setOffset(0)
  }

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Toggle sort order if same column clicked
      setSortOrder(sortOrder === "asc" ? "desc" : "asc")
    } else {
      // New column, sort ascending
      setSortColumn(column)
      setSortOrder("asc")
    }
  }

  const handleRefresh = () => {
    setOffset(0)
    fetchTickets()
  }

  const getSortedTickets = (sourceTickets: Ticket[]) => {
    if (!sortColumn) return sourceTickets

    return [...sourceTickets].sort((a, b) => {
      let aVal: string | number | Date = a[sortColumn as keyof Ticket] as string | number | Date
      let bVal: string | number | Date = b[sortColumn as keyof Ticket] as string | number | Date

      if (sortColumn === "open_duration") {
        const getOpenDays = (ticket: Ticket) => {
          const created = new Date(ticket.created_at)
          const closed = ticket.closed_at ? new Date(ticket.closed_at) : new Date()
          return (closed.getTime() - created.getTime()) / (1000 * 60 * 60 * 24)
        }
        aVal = getOpenDays(a)
        bVal = getOpenDays(b)
      }

      if (aVal < bVal) return sortOrder === "asc" ? -1 : 1
      if (aVal > bVal) return sortOrder === "asc" ? 1 : -1
      return 0
    })
  }

  const fetchAllFilteredTickets = async () => {
    const allTickets: Ticket[] = []
    let nextOffset = 0
    let expectedTotal = 0

    do {
      const result = await ticketService.getTickets(
        EXPORT_PAGE_SIZE,
        nextOffset,
        statusFilter || undefined,
        undefined,
        companyFilter || undefined,
        levelFilter || undefined
      )

      allTickets.push(...result.tickets)
      expectedTotal = result.total
      nextOffset += EXPORT_PAGE_SIZE
    } while (allTickets.length < expectedTotal)

    return getSortedTickets(allTickets)
  }

  const exportToExcel = async () => {
    try {
      // Dynamically import the date utility
      const { calculateTicketOpenDuration } = await import("@/lib/date-utils")

      const filteredTickets = await fetchAllFilteredTickets()
      if (filteredTickets.length === 0) {
        alert("No tickets to export")
        return
      }
      
      // Fetch full details for all tickets to get complete data
      const ticketDetails = await Promise.all(
        filteredTickets.map(ticket => ticketService.getTicketById(ticket.id))
      )
      
      const exportData = ticketDetails.map((ticket) => {
        const attachments = ticket.attachments || []
        const attachmentNames = attachments.map(a => fileNameFromPath(a.file_path))
        const attachmentTypes = attachments.map(a => a.mime_type || a.type || "unknown")
        const attachmentLinks = attachments.map(a => {
          if (a.file_path?.startsWith("http")) return a.file_path
          return `${window.location.origin}/api/tickets/${ticket.id}/attachments/${a.id}/download`
        })
        
        // Format RCA data
        const rca = ticket.rca || ticket.root_cause_analysis
        const rcaContributingFactors = rca?.contributing_factors?.join("; ") || "-"
        const rcaResolutionSteps = rca?.resolution_steps?.join("; ") || "-"
        const rcaAttachmentLinks = rca?.attachments?.map(a => a.file_path) || []
        const rcaAttachmentNames = rca?.attachments?.map(a => fileNameFromPath(a.file_path)) || []
        
        // Format ResolutionNote data
        const resolutionNote = ticket.resolution_note
        const resolutionStepsTaken = resolutionNote?.steps_taken?.join("; ") || "-"
        const resolutionResourcesUsed = resolutionNote?.resources_used?.join("; ") || "-"
        
        return {
          "Ticket #": ticket.ticket_no,
          "Subject": ticket.subject,
          "Summary": ticket.summary || "-",
          "Description": ticket.detailed_description || "-",
          "Category": ticket.category || "-",
          "Level": ticket.level || "-",
          "Status": ticket.status,
          "Company": ticket.company_name || "-",
          "Created By": ticket.created_by || "-",
          "Created By ID": ticket.created_by_id || "-",
          "Assigned To": ticket.assigned_to || "Unassigned",
          "Assigned To ID": ticket.assigned_to_id || "-",
          "Created At": formatDate(ticket.created_at),
          "Updated At": formatDate(ticket.updated_at),
          "Closed At": formatDate(ticket.closed_at),
          "Reopened At": formatDate(ticket.reopened_at),
          "Open For": calculateTicketOpenDuration(ticket.created_at, ticket.closed_at).formatted,
          "Has IR": ticket.has_ir ? "Yes" : "No",
          "IR Number": ticket.ir_number || "-",
          "IR Raised At": formatDate(ticket.ir_raised_at),
          "IR Expected Resolution": formatDate(ticket.ir_expected_resolution_date),
          "IR Notes": ticket.ir_notes || "-",
          "IR Closed At": formatDate(ticket.ir_closed_at),
          "Attachment Names": joinList(attachmentNames),
          "Attachment Types": joinList(attachmentTypes),
          "Attachment Links": joinList(attachmentLinks),
          "Attachments Count": attachments.length,
          "RCA Root Cause": rca?.root_cause_description || rca?.root_cause || "-",
          "RCA Contributing Factors": rcaContributingFactors,
          "RCA Prevention Measures": rca?.prevention_measures || "-",
          "RCA Resolution Steps": rcaResolutionSteps,
          "RCA Attachment Names": joinList(rcaAttachmentNames),
          "RCA Attachment Links": joinList(rcaAttachmentLinks),
          "RCA Attachments Count": rca?.attachments?.length || 0,
          "Resolution Solution": resolutionNote?.solution_description || "-",
          "Resolution Steps Taken": resolutionStepsTaken,
          "Resolution Resources Used": resolutionResourcesUsed,
          "Resolution Follow-up Notes": resolutionNote?.follow_up_notes || "-",
          "Events Count": ticket.events?.length || 0,
        }
      })

      const csv = `\uFEFF${buildCsv(exportData)}`

      // Download as CSV file
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
      const link = document.createElement("a")
      const url = URL.createObjectURL(blob)
      link.setAttribute("href", url)
      link.setAttribute("download", `tickets_${new Date().toISOString().split("T")[0]}.csv`)
      link.style.visibility = "hidden"
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (err) {
      console.error("Failed to export tickets:", err)
      alert("Failed to export tickets")
    }
  }

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header with Create Button and Export */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Tickets</h1>
            <p className="text-gray-600 mt-1">
              {total > 0
                ? `Showing ${offset + 1}-${Math.min(offset + limit, total)} of ${total} tickets`
                : "No tickets found"}
            </p>
          </div>
          <div className="flex gap-2">
            {isAuthenticated && admin && (
              <CreateTicketDialog
                currentUserId={admin.id}
                onTicketCreated={handleRefresh}
              />
            )}
            <Button
              onClick={exportToExcel}
              disabled={tickets.length === 0}
              className="bg-green-600 hover:bg-green-700"
            >
              <Download className="mr-2 h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>

        {/* Filters Row 1 - Status, Level, Company (3-column layout) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700 block mb-2">Status Filter</label>
            <div className="flex gap-2">
              <Select
                value={statusFilter || "all"}
                onValueChange={(value) =>
                  handleStatusFilter(value === "all" ? null : value)
                }
              >
                <SelectTrigger className="flex-1">
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
                  title="Clear status filter"
                >
                  ✕
                </Button>
              )}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-2">Level Filter</label>
            <div className="flex gap-2">
              <Select
                value={levelFilter || "all"}
                onValueChange={(value) =>
                  handleLevelFilter(value === "all" ? null : value)
                }
              >
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Filter by level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  {LEVEL_FILTERS.map((filter) => (
                    <SelectItem key={filter.value} value={filter.value}>
                      {filter.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {levelFilter && (
                <Button
                  variant="outline"
                  onClick={() => handleLevelFilter(null)}
                  className="px-2"
                  title="Clear level filter"
                >
                  ✕
                </Button>
              )}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-2">Company Filter</label>
            <div className="flex gap-2">
              <Select
                value={companyFilter || "all"}
                onValueChange={(value) =>
                  handleCompanyFilter(value === "all" ? null : value)
                }
              >
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Filter by company" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Companies</SelectItem>
                  {companies.map((company) => (
                    <SelectItem key={company.id} value={company.id}>
                      {company.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {companyFilter && (
                <Button
                  variant="outline"
                  onClick={() => handleCompanyFilter(null)}
                  className="px-2"
                  title="Clear company filter"
                >
                  ✕
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Sort Options */}
        <div className="flex gap-2 items-center">
          <span className="text-sm font-medium text-gray-700">Sort by:</span>
          <Button
            variant={sortColumn === "ticket_no" ? "default" : "outline"}
            size="sm"
            onClick={() => handleSort("ticket_no")}
          >
            Ticket # {sortColumn === "ticket_no" && (sortOrder === "asc" ? "↑" : "↓")}
          </Button>
          <Button
            variant={sortColumn === "created_at" ? "default" : "outline"}
            size="sm"
            onClick={() => handleSort("created_at")}
          >
            Created {sortColumn === "created_at" && (sortOrder === "asc" ? "↑" : "↓")}
          </Button>
          <Button
            variant={sortColumn === "open_duration" ? "default" : "outline"}
            size="sm"
            onClick={() => handleSort("open_duration")}
          >
            Open For {sortColumn === "open_duration" && (sortOrder === "asc" ? "↑" : "↓")}
          </Button>
          {sortColumn && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSortColumn(null)}
              className="ml-auto"
            >
              Clear Sort
            </Button>
          )}
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
