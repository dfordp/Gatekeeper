"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Clock, ChevronRight } from "lucide-react"
import { calculateTicketOpenDuration } from "@/lib/date-utils"

interface Ticket {
  id: string
  ticket_no: string
  subject: string
  status: string
  level?: string | null
  created_at: string
}

interface LongestOpenTicketProps {
  ticket: Ticket | null
}

const levelColors: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
}

export default function LongestOpenTicket({ ticket }: LongestOpenTicketProps) {
  if (!ticket) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Longest Open Ticket
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500">No open tickets</p>
        </CardContent>
      </Card>
    )
  }

  const duration = calculateTicketOpenDuration(ticket.created_at)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Longest Open Ticket
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <p className="text-sm text-gray-600 mb-1">Ticket #</p>
            <p className="text-2xl font-bold text-gray-900">{ticket.ticket_no}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 mb-1">Subject</p>
            <p className="text-gray-900 line-clamp-2">{ticket.subject}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-3xl font-bold text-orange-600">
              {duration.days}
            </span>
            <span className="text-gray-600">days open</span>
          </div>
          <div className="flex gap-2">
            {ticket.level && (
              <Badge className={levelColors[ticket.level] || "bg-blue-100"}>
                {ticket.level}
              </Badge>
            )}
          </div>
          <Link href={`/dashboard/tickets/${ticket.id}`}>
            <Button className="w-full">
              View Ticket <ChevronRight className="h-4 w-4 ml-2" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
