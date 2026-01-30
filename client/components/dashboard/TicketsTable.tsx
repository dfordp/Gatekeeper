// client/components/dashboard/TicketsTable.tsx
"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { RefreshCw, ChevronRight, Inbox } from "lucide-react"

interface Ticket {
  id: string
  ticket_no: string
  subject: string
  status: string
  category?: string | null
  level?: string | null
  company_name?: string | null
  created_by?: string | null
  created_at: string
}

interface TicketsTableProps {
  tickets: Ticket[] | null | undefined
  onRefresh: () => void
}

const statusColors: Record<string, string> = {
  open: "bg-red-100 text-red-800",
  in_progress: "bg-yellow-100 text-yellow-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-800",
  reopened: "bg-orange-100 text-orange-800",
}

const levelColors: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
}

const EmptyState = () => (
  <div className="flex flex-col items-center justify-center py-12">
    <Inbox className="h-12 w-12 text-gray-400 mb-4" />
    <h3 className="text-lg font-medium text-gray-900 mb-1">No tickets found</h3>
    <p className="text-gray-500">There are no tickets to display at this time.</p>
  </div>
)

export default function TicketsTable({ tickets, onRefresh }: TicketsTableProps) {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    await onRefresh()
    setRefreshing(false)
  }

  const ticketList = tickets && Array.isArray(tickets) ? tickets : []
  const hasTickets = ticketList.length > 0

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Tickets</CardTitle>
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
        {!hasTickets ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4">Ticket #</th>
                  <th className="text-left py-3 px-4">Subject</th>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-left py-3 px-4">Level</th>
                  <th className="text-left py-3 px-4">Company</th>
                  <th className="text-left py-3 px-4">Created</th>
                  <th className="text-right py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {ticketList.map((ticket) => (
                  <tr key={ticket.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium">{ticket.ticket_no}</td>
                    <td className="py-3 px-4">{ticket.subject || <span className="text-gray-400 italic">No subject</span>}</td>
                    <td className="py-3 px-4">
                      <Badge className={statusColors[ticket.status] || "bg-gray-100"}>
                        {ticket.status}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      {ticket.level ? (
                        <Badge className={levelColors[ticket.level] || "bg-blue-100"}>
                          {ticket.level}
                        </Badge>
                      ) : (
                        <span className="text-gray-400 text-xs">Unset</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {ticket.company_name || <span className="text-gray-400 italic">Unknown</span>}
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {ticket.created_at
                        ? new Date(ticket.created_at).toLocaleDateString()
                        : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Link href={`/dashboard/tickets/${ticket.id}`}>
                        <Button variant="ghost" size="sm">
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </Link>
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