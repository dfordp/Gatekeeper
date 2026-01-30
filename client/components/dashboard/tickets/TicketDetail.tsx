// client/components/dashboard/tickets/TicketDetail.tsx - UPDATE IMPORTS AND API CALLS

"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2, ArrowLeft, AlertCircle } from "lucide-react"
import { ticketService, TicketDetail as TicketDetailType } from "@/services/ticket.service"
import TicketTimeline from "./TicketTimeline"
import TicketActions from "./TicketActions"

interface TicketDetailProps {
  ticketId: string
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

export default function TicketDetail({ ticketId }: TicketDetailProps) {
  const router = useRouter()
  const [ticket, setTicket] = useState<TicketDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    fetchTicket()
  }, [ticketId])

  const fetchTicket = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await ticketService.getTicketById(ticketId)
      setTicket(result)
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load ticket")
    } finally {
      setLoading(false)
    }
  }

  const handleStatusChange = async (newStatus: string) => {
    if (!ticket) return
    try {
      setActionLoading(true)
      await ticketService.updateStatus(ticketId, newStatus)
      setTicket({ ...ticket, status: newStatus as any })
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to update status")
    } finally {
      setActionLoading(false)
    }
  }

  const handleAssign = async (engineerId: string) => {
    if (!ticket) return
    try {
      setActionLoading(true)
      const response = await ticketService.assignTicket(ticketId, engineerId)
      setTicket({
        ...ticket,
        assigned_to: response.assigned_to,
        assigned_to_id: response.assigned_to_id,
      })
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to assign ticket")
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (error || !ticket) {
    return (
      <div className="space-y-4">
        <Button variant="outline" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Tickets
        </Button>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error || "Ticket not found"}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Tickets
        </Button>
        <div className="flex gap-2">
          <Badge className={statusColors[ticket.status] || "bg-gray-100"}>
            {ticket.status}
          </Badge>
          {ticket.level && (
            <Badge className={levelColors[ticket.level] || "bg-blue-100"}>
              {ticket.level}
            </Badge>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left Column - Ticket Info */}
        <div className="col-span-2 space-y-6">
          {/* Ticket Header */}
          <Card>
            <CardHeader>
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-500">Ticket #</p>
                  <h1 className="text-3xl font-bold text-gray-900">
                    {ticket.ticket_no}
                  </h1>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Subject</p>
                  <h2 className="text-xl font-semibold text-gray-900">
                    {ticket.subject}
                  </h2>
                </div>
                {ticket.summary && (
                  <div>
                    <p className="text-sm text-gray-500">Summary</p>
                    <p className="text-gray-700">{ticket.summary}</p>
                  </div>
                )}
              </div>
            </CardHeader>
          </Card>

          {/* Detailed Description */}
          <Card>
            <CardHeader>
              <CardTitle>Description</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-gray-700 whitespace-pre-wrap">
                {ticket.detailed_description}
              </p>
            </CardContent>
          </Card>

          {/* Timeline */}
          <TicketTimeline events={ticket.events} />
        </div>

        {/* Right Column - Sidebar */}
        <div className="space-y-6">
          {/* Ticket Actions */}
          <TicketActions
            ticket={ticket}
            onStatusChange={handleStatusChange}
            onAssign={handleAssign}
            isLoading={actionLoading}
          />

          {/* Metadata */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  Company
                </p>
                <p className="text-sm text-gray-900">
                  {ticket.company_name || "—"}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  Category
                </p>
                <p className="text-sm text-gray-900">
                  {ticket.category || "Uncategorized"}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  Created By
                </p>
                <p className="text-sm text-gray-900">
                  {ticket.created_by || "—"}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  Created
                </p>
                <p className="text-sm text-gray-900">
                  {new Date(ticket.created_at).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  Updated
                </p>
                <p className="text-sm text-gray-900">
                  {new Date(ticket.updated_at).toLocaleString()}
                </p>
              </div>
              {ticket.closed_at && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase">
                    Closed
                  </p>
                  <p className="text-sm text-gray-900">
                    {new Date(ticket.closed_at).toLocaleString()}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}