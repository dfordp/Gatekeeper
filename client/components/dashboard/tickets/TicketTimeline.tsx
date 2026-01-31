// client/components/dashboard/tickets/TicketTimeline.tsx

"use client"

import { ReactNode } from "react"
import { TicketEvent } from "@/types/index"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  CheckCircle,
  MessageCircle,
  AlertCircle,
  Clock,
  FileText,
} from "lucide-react"

interface TicketTimelineProps {
  events: TicketEvent[]
}

const eventIcons: Record<string, ReactNode> = {
  status_updated: <CheckCircle className="h-5 w-5 text-blue-600" />,
  comment_added: <MessageCircle className="h-5 w-5 text-green-600" />,
  assigned: <AlertCircle className="h-5 w-5 text-purple-600" />,
  attachment_added: <FileText className="h-5 w-5 text-orange-600" />,
  rca_added: <AlertCircle className="h-5 w-5 text-red-600" />,
  ticket_created: <Clock className="h-5 w-5 text-gray-600" />,
  default: <Clock className="h-5 w-5 text-gray-600" />,
}

export default function TicketTimeline({ events }: TicketTimelineProps) {
  if (!events || events.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-500">No activity yet</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {events.map((event, index) => (
            <div key={event.id} className="flex gap-4">
              {/* Timeline Line */}
              <div className="flex flex-col items-center">
                <div className="p-2 bg-gray-100 rounded-full">
                  {eventIcons[event.type] || eventIcons.default}
                </div>
                {index < events.length - 1 && (
                  <div className="w-0.5 h-12 bg-gray-200 mt-2" />
                )}
              </div>

              {/* Event Content */}
              <div className="flex-1 pt-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-semibold text-gray-900">
                    {event.actor_name || "System"}
                  </p>
                  <p className="text-xs text-gray-500">
                    {new Date(event.created_at).toLocaleString()}
                  </p>
                </div>
                <p className="text-sm text-gray-600 mb-2">
                  {formatEventDescription(event)}
                </p>
                {event.payload && (
                  <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600">
                    {formatPayload(event)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function formatEventType(type: string): string {
  const types: Record<string, string> = {
    status_updated: "Updated ticket status",
    comment_added: "Added a comment",
    assigned: "Assigned ticket",
    attachment_added: "Added attachment",
    rca_added: "Added Root Cause Analysis",
    ticket_created: "Created ticket",
  }
  return types[type] || type.replace(/_/g, " ")
}

function formatEventDescription(event: TicketEvent): string {
  const type = event.type
  switch (type) {
    case "attachment_added":
      return `Added attachment: ${event.payload?.file_name || "unknown file"}`
    case "status_updated":
      return `Changed status to ${event.payload?.new_status || "unknown"}`
    case "assigned":
      return `Assigned to ${event.payload?.assigned_to || "unknown"}`
    case "rca_added":
      return "Added Root Cause Analysis"
    case "ticket_created":
      return "Created ticket"
    default:
      return formatEventType(type)
  }
}

function formatPayload(event: TicketEvent): string {
  if (!event.payload) return ""
  
  switch (event.type) {
    case "attachment_added":
      const { file_name, file_size, type } = event.payload
      const sizeStr = file_size ? `${(Number(file_size) / 1024).toFixed(2)} KB` : "unknown size"
      return `${file_name} (${type}, ${sizeStr})`
    case "ticket_created":
      return `Category: ${event.payload.category || "N/A"} | Level: ${event.payload.level || "N/A"}`
    case "rca_added":
      return `Factors: ${event.payload.factors_count || 0} | Steps: ${event.payload.steps_count || 0}`
    default:
      return JSON.stringify(event.payload, null, 2)
  }
}