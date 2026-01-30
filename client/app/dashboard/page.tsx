// client/app/dashboard/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import AnalyticsCards from "@/components/dashboard/AnalyticsCards"
import TicketsTable from "@/components/dashboard/TicketsTable"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Loader2 } from "lucide-react"

interface Analytics {
  total_tickets: number
  open_tickets: number
  in_progress: number
  resolved: number
  closed: number
  recent_tickets: number
  avg_resolution_time_hours: number
  categories: Record<string, number>
  levels: Record<string, number>
  [key: string]: unknown
}

interface Ticket {
  id: string
  ticket_no: string
  subject: string
  status: string
  created_at: string
  [key: string]: unknown
}

export default function DashboardPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuth()
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [ticketsLoading, setTicketsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  useEffect(() => {
    if (isAuthenticated) {
      fetchAnalytics()
      fetchTickets()
    }
  }, [isAuthenticated])

  const fetchAnalytics = async () => {
    try {
      setError(null)
      const token = localStorage.getItem("auth_token")
      const response = await fetch("/api/dashboard/analytics", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (!response.ok) {
        throw new Error("Failed to fetch analytics")
      }
      const data = await response.json()
      setAnalytics(data)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error"
      setError(message)
      setAnalytics(null)
    } finally {
      setAnalyticsLoading(false)
    }
  }

  const fetchTickets = async () => {
    try {
      setError(null)
      const token = localStorage.getItem("auth_token")
      const response = await fetch("/api/dashboard/tickets?limit=20", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (!response.ok) {
        throw new Error("Failed to fetch tickets")
      }
      const data = await response.json()
      setTickets(data.tickets || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error"
      setError(message)
      setTickets([])
    } finally {
      setTicketsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-gray-600">
            Welcome to the support ticket management system
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {analyticsLoading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : (
          <AnalyticsCards analytics={analytics} />
        )}

        <div>
          <h2 className="text-2xl font-bold mb-4">Recent Tickets</h2>
          {ticketsLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <TicketsTable tickets={tickets} onRefresh={fetchTickets} />
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}