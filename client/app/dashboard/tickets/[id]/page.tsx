// client/app/dashboard/tickets/[id]/page.tsx

"use client"

import { useAuth } from "@/hooks/useAuth"
import DashboardLayout from "@/components/dashboard/DashboardLayout"
import TicketDetail from "@/components/dashboard/tickets/TicketDetail"
import { useRouter } from "next/navigation"
import { useEffect } from "react"

export default function TicketDetailPage({
  params,
}: {
  params: { id: string }
}) {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuth()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isLoading, router])

  if (isLoading) {
    return null
  }

  return (
    <DashboardLayout>
      <TicketDetail ticketId={params.id} />
    </DashboardLayout>
  )
}