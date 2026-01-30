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
                    {event.actor || "System"}
                  </p>
                  <p className="text-xs text-gray-500">
                    {new Date(event.created_at).toLocaleString()}
                  </p>
                </div>
                <p className="text-sm text-gray-600">
                  {formatEventType(event.type)}
                </p>
                {event.payload && (
                  <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-700">
                    {JSON.stringify(event.payload, null, 2)}
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
  }
  return types[type] || type.replace(/_/g, " ")
}