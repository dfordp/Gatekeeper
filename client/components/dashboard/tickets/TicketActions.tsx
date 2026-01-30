// client/components/dashboard/tickets/TicketActions.tsx - UPDATE IMPORTS AND API CALLS

"use client"

import { useState, useEffect } from "react"
import { TicketDetail } from "@/services/ticket.service"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, CheckCircle, Clock, AlertCircle } from "lucide-react"
import { userService, User } from "@/services/user.service"

interface TicketActionsProps {
  ticket: TicketDetail
  onStatusChange: (status: string) => Promise<void>
  onAssign: (engineerId: string) => Promise<void>
  isLoading: boolean
}

const STATUS_OPTIONS = [
  { value: "open", label: "Open", icon: AlertCircle },
  { value: "in_progress", label: "In Progress", icon: Clock },
  { value: "resolved", label: "Resolved", icon: CheckCircle },
  { value: "closed", label: "Closed", icon: CheckCircle },
  { value: "reopened", label: "Reopened", icon: AlertCircle },
]

export default function TicketActions({
  ticket,
  onStatusChange,
  onAssign,
  isLoading,
}: TicketActionsProps) {
  const [engineers, setEngineers] = useState<User[]>([])
  const [loadingEngineers, setLoadingEngineers] = useState(true)

  useEffect(() => {
    fetchEngineers()
  }, [])

  const fetchEngineers = async () => {
    try {
      const result = await userService.getUsers()
      setEngineers(
        result.users?.filter(
          (u) => u.role === "support_engineer" || u.role === "supervisor"
        ) || []
      )
    } catch (err) {
      console.error("Failed to load engineers:", err)
    } finally {
      setLoadingEngineers(false)
    }
  }

  const handleStatusChange = async (newStatus: string) => {
    if (newStatus === ticket.status) return
    await onStatusChange(newStatus)
  }

  const handleAssign = async (engineerId: string) => {
    if (engineerId === (ticket.assigned_to_id || "")) return
    await onAssign(engineerId)
  }

  return (
    <div className="space-y-4">
      {/* Status Update */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Change Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {STATUS_OPTIONS.map((option) => (
            <Button
              key={option.value}
              variant={
                ticket.status === option.value ? "default" : "outline"
              }
              className="w-full justify-start"
              onClick={() => handleStatusChange(option.value)}
              disabled={isLoading || ticket.status === option.value}
            >
              <option.icon className="h-4 w-4 mr-2" />
              {option.label}
              {isLoading && ticket.status !== option.value && (
                <Loader2 className="h-4 w-4 ml-auto animate-spin" />
              )}
            </Button>
          ))}
        </CardContent>
      </Card>

      {/* Assign to Engineer */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assign To</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingEngineers ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-gray-500" />
            </div>
          ) : engineers.length > 0 ? (
            <Select
              value={ticket.assigned_to_id || ""}
              onValueChange={handleAssign}
              disabled={isLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select engineer..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Unassigned</SelectItem>
                {engineers.map((engineer) => (
                  <SelectItem key={engineer.id} value={engineer.id}>
                    {engineer.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <p className="text-sm text-gray-500">No engineers available</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}