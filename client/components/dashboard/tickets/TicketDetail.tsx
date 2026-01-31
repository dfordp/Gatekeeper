// client/components/dashboard/tickets/TicketDetail.tsx

"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { Loader2, ArrowLeft, AlertCircle, Trash2, Edit2, FileText, Zap, Download } from "lucide-react"
import { ticketService, TicketDetail as TicketDetailType } from "@/services/ticket.service"
import TicketTimeline from "./TicketTimeline"
import TicketActions from "./TicketActions"
import EditTicketDialog from "./EditTicketDialog"

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
  "level-1": "bg-red-100 text-red-800",
  "level-2": "bg-orange-100 text-orange-800",
  "level-3": "bg-yellow-100 text-yellow-800",
}

const isImageFile = (filename: string): boolean => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']
  return imageExtensions.some(ext => filename.toLowerCase().endsWith(ext))
}

export default function TicketDetail({ ticketId }: TicketDetailProps) {
  const router = useRouter()
  const [ticket, setTicket] = useState<TicketDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

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

  const handleDeleteTicket = async () => {
    try {
      setActionLoading(true)
      await ticketService.deleteTicket(ticketId)
      router.push("/dashboard/tickets")
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to delete ticket")
    } finally {
      setActionLoading(false)
      setShowDeleteConfirm(false)
    }
  }

  const handleEditTicket = async (data: any) => {
    try {
      setActionLoading(true)
      const updated = await ticketService.updateTicket(ticketId, data)
      setTicket({ ...ticket, ...updated } as TicketDetailType)
      setShowEditDialog(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to update ticket")
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
        <div className="flex items-center gap-4">
          <Button variant="outline" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              {ticket.ticket_no}
            </h1>
            <p className="text-sm text-gray-500">{ticket.subject}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
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

      {/* Action Buttons */}
      <div className="flex gap-2">
        <Button
          onClick={() => setShowEditDialog(true)}
          variant="outline"
          size="sm"
        >
          <Edit2 className="h-4 w-4 mr-2" />
          Edit
        </Button>
        <Button
          onClick={() => setShowDeleteConfirm(true)}
          variant="destructive"
          size="sm"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          Delete
        </Button>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="ticket" className="w-full">
        <TabsList className={`grid w-full ${ticket.rca ? 'grid-cols-3' : 'grid-cols-2'}`}>
          <TabsTrigger value="ticket" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Ticket
          </TabsTrigger>
          {ticket.rca && (
            <TabsTrigger value="rca" className="flex items-center gap-2">
              <Zap className="h-4 w-4" />
              RCA
            </TabsTrigger>
          )}
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        {/* Ticket Tab */}
        <TabsContent value="ticket" className="space-y-6">
          <div className="grid grid-cols-3 gap-6">
            {/* Left Column */}
            <div className="col-span-2 space-y-6">
              {/* Description */}
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

              {/* Attachments */}
              {ticket.attachments && ticket.attachments.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Attachments</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {ticket.attachments.map((attachment) => {
                        const displayName = attachment.file_path?.split('/').pop() || attachment.file_path
                        const isImage = isImageFile(displayName)
                        const downloadUrl = `/api/tickets/${ticketId}/attachments/${attachment.id}/download`

                        return (
                          <div
                            key={attachment.id}
                            className="border rounded-lg overflow-hidden"
                          >
                            {/* Image Rendering */}
                            {isImage && (
                              <div className="mb-3">
                                <img
                                  src={downloadUrl}
                                  alt={displayName}
                                  className="max-w-full max-h-96 object-contain rounded"
                                  onError={(e) => {
                                    console.error(`Failed to load image: ${displayName}`)
                                  }}
                                />
                              </div>
                            )}

                            {/* File Info */}
                            <div className="p-3 bg-gray-50 flex items-center justify-between">
                              <div>
                                <p className="text-sm font-medium text-gray-900">
                                  {displayName}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {attachment.type}
                                </p>
                              </div>
                              <a
                                href={downloadUrl}
                                className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-sm"
                                download
                              >
                                <Download className="h-4 w-4" />
                                Download
                              </a>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Right Column */}
            <div className="space-y-6">
              <TicketActions
                ticket={ticket}
                onStatusChange={handleStatusChange}
                onAssign={handleAssign}
                isLoading={actionLoading}
              />

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
                      {ticket.category || "—"}
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
        </TabsContent>

        {/* RCA Tab */}
        {ticket.rca && (
          <TabsContent value="rca" className="space-y-6">
            <Card>
              {ticket.rca.ticket_closed_at && (
                <p className="text-xs text-gray-500 mt-2">
                  Ticket closed: {new Date(ticket.rca.ticket_closed_at).toLocaleString()}
                </p>
              )}
              <CardHeader>
                <CardTitle>Root Cause Analysis</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm font-semibold text-gray-700 mb-2">
                    Root Cause
                  </p>
                  <p className="text-gray-700">
                    {ticket.rca.root_cause_description}
                  </p>
                </div>

                {ticket.rca.contributing_factors &&
                  ticket.rca.contributing_factors.length > 0 && (
                    <div>
                      <p className="text-sm font-semibold text-gray-700 mb-2">
                        Contributing Factors
                      </p>
                      <ul className="list-disc list-inside space-y-1">
                        {ticket.rca.contributing_factors.map((factor, i) => (
                          <li key={i} className="text-gray-700">
                            {factor}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                {ticket.rca.prevention_measures && (
                  <div>
                    <p className="text-sm font-semibold text-gray-700 mb-2">
                      Prevention Measures
                    </p>
                    <p className="text-gray-700">
                      {ticket.rca.prevention_measures}
                    </p>
                  </div>
                )}

                {ticket.rca.resolution_steps &&
                  ticket.rca.resolution_steps.length > 0 && (
                    <div>
                      <p className="text-sm font-semibold text-gray-700 mb-2">
                        Resolution Steps
                      </p>
                      <ol className="list-decimal list-inside space-y-1">
                        {ticket.rca.resolution_steps.map((step, i) => (
                          <li key={i} className="text-gray-700">
                            {step}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
              </CardContent>
            </Card>

            {ticket.resolution && (
              <Card>
                <CardHeader>
                  <CardTitle>Resolution</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <p className="text-sm font-semibold text-gray-700 mb-2">
                      Solution
                    </p>
                    <p className="text-gray-700">
                      {ticket.resolution.solution_description}
                    </p>
                  </div>

                  {ticket.resolution.steps_taken &&
                    ticket.resolution.steps_taken.length > 0 && (
                      <div>
                        <p className="text-sm font-semibold text-gray-700 mb-2">
                          Steps Taken
                        </p>
                        <ol className="list-decimal list-inside space-y-1">
                          {ticket.resolution.steps_taken.map((step, i) => (
                            <li key={i} className="text-gray-700">
                              {step}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}

                  {ticket.resolution.resources_used &&
                    ticket.resolution.resources_used.length > 0 && (
                      <div>
                        <p className="text-sm font-semibold text-gray-700 mb-2">
                          Resources Used
                        </p>
                        <ul className="list-disc list-inside space-y-1">
                          {ticket.resolution.resources_used.map((res, i) => (
                            <li key={i} className="text-gray-700">
                              {res}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                </CardContent>
              </Card>
            )}
          </TabsContent>
        )}

        {/* Activity Tab */}
        <TabsContent value="activity">
          <TicketTimeline events={ticket.events} />
        </TabsContent>
      </Tabs>

      {/* Edit Dialog */}
      <EditTicketDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        ticket={ticket}
        onSave={handleEditTicket}
        fetchTicket={fetchTicket}  // Add this
        isLoading={actionLoading}
      />

      {/* Delete Confirmation */}
      {showDeleteConfirm && (
        <Alert variant="destructive" className="fixed bottom-4 right-4 w-96">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex items-center justify-between">
            <span>Are you sure you want to delete this ticket?</span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={handleDeleteTicket}
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Delete"
                )}
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}