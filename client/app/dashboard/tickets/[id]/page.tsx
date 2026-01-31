// client/app/dashboard/tickets/[id]/page.tsx

"use client"

import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import TicketDetail from "@/components/dashboard/tickets/TicketDetail"
import { useRouter, useParams } from "next/navigation"
import { useEffect } from "react"

export default function TicketDetailPage() {
  const router = useRouter()
  const params = useParams()
  const ticketId = params?.id as string
  const { isAuthenticated, isLoading } = useAuth()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  if (isLoading || !ticketId) {
    return null
  }

  return (
    <DashboardLayout>
      <TicketDetail ticketId={ticketId} />
    </DashboardLayout>
  )
}