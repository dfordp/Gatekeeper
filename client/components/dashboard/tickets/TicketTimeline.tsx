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
  Edit,
  Trash2,
} from "lucide-react"

interface TicketTimelineProps {
  events: TicketEvent[]
}

const eventIcons: Record<string, ReactNode> = {
  ticket_created: <Clock className="h-5 w-5 text-gray-600" />,
  ticket_updated: <Edit className="h-5 w-5 text-blue-600" />,
  status_updated: <CheckCircle className="h-5 w-5 text-green-600" />,
  attachment_added: <FileText className="h-5 w-5 text-orange-600" />,
  attachment_deleted: <Trash2 className="h-5 w-5 text-red-500" />,
  rca_added: <AlertCircle className="h-5 w-5 text-red-600" />,
  rca_updated: <Edit className="h-5 w-5 text-red-600" />,
  ticket_assigned: <AlertCircle className="h-5 w-5 text-purple-600" />,
  ticket_unassigned: <AlertCircle className="h-5 w-5 text-gray-600" />,
  comment_added: <MessageCircle className="h-5 w-5 text-green-600" />,
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

  // Reverse events to show latest first
  const sortedEvents = [...events].reverse()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {sortedEvents.map((event, index) => (
            <div key={event.id} className="flex gap-4">
              {/* Timeline Line */}
              <div className="flex flex-col items-center">
                <div className="p-2 bg-gray-100 rounded-full">
                  {eventIcons[event.type] || eventIcons.default}
                </div>
                {index < sortedEvents.length - 1 && (
                  <div className="w-0.5 h-12 bg-gray-200 mt-2" />
                )}
              </div>

              {/* Event Content */}
              <div className="flex-1 pt-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-semibold text-gray-900">
                    System
                  </p>
                  <p className="text-xs text-gray-500">
                    {new Date(event.created_at).toLocaleString()}
                  </p>
                </div>
                <p className="text-sm text-gray-600 mb-2">
                  {formatEventDescription(event)}
                </p>
                {event.payload && Object.keys(event.payload).length > 0 && (
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

function formatEventDescription(event: TicketEvent): string {
  const { type, payload } = event
  
  switch (type) {
    case "ticket_created":
      return "Created ticket"
    case "ticket_updated":
      return "Updated ticket details"
    case "status_updated":
      return `Changed status from ${payload?.from || "unknown"} to ${payload?.to || "unknown"}`
    case "attachment_added":
      return `Added attachment: ${payload?.file_name || "unknown file"}`
    case "attachment_deleted":
      return `Deleted attachment: ${payload?.file_name || "unknown file"}`
    case "rca_added":
      return "Added Root Cause Analysis"
    case "rca_updated":
      return "Updated Root Cause Analysis"
    case "ticket_assigned":
      return `Assigned to ${payload?.assigned_to || "unknown"}`
    case "ticket_unassigned":
      return `Unassigned from ${payload?.previous_assignee || "unknown"}`
    case "comment_added":
      return "Added a comment"
    default:
      return type.replace(/_/g, " ")
  }
}

function formatPayload(event: TicketEvent): string {
  if (!event.payload) return ""
  
  const { type, payload } = event

  switch (type) {
    case "attachment_added":
      const { file_name, file_size, type: attachType } = payload
      const sizeStr = file_size ? `${(Number(file_size) / 1024).toFixed(2)} KB` : "unknown size"
      return `${file_name} (${attachType}, ${sizeStr})`
    
    case "ticket_updated":
      const changes = payload.changes
      if (changes && typeof changes === "object") {
        return Object.entries(changes)
          .map(([key, value]: [string, unknown]) => {
            if (typeof value === "object" && value !== null && "from" in value && "to" in value) {
              return `${key}: "${(value as Record<string, unknown>).from}" → "${(value as Record<string, unknown>).to}"`
            }
            return `${key}: ${JSON.stringify(value)}`
          })
          .join(" | ")
      }
      return JSON.stringify(payload)
    
    case "ticket_created":
      return `Category: ${payload.category || "N/A"} | Level: ${payload.level || "N/A"}`
    
    case "rca_added":
    case "rca_updated":
      return `Factors: ${payload.factors_count || 0} | Steps: ${payload.steps_count || 0}`
    
    case "status_updated":
      return `${payload.from} → ${payload.to}`
    
    default:
      return JSON.stringify(payload, null, 2)
  }
}